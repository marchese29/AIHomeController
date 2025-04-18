import abc
import asyncio as aio
from datetime import datetime, time, timedelta
from typing import Any, Callable, Optional

from hubitat.client import HubitatClient, HubitatDevice
from hubitat.rules.conditions import (
    AbstractCondition,
    AttributeChangeCondition,
    BooleanCondition,
    DynamicDeviceAttributeCondition,
    StaticDeviceAttributeCondition,
)
from hubitat.rules.engine import RuleEngine


class Attribute:
    """An attribute of a device."""

    def __init__(self, device_id: int, attr_name: str):
        self._device_id = device_id
        self._attr_name = attr_name

    def _compare(self, other: Any, op: str) -> AbstractCondition:
        """Helper method to handle all comparison operations.

        Args:
            other: Value to compare against
            op: Comparison operator to use
        Returns:
            Appropriate condition object for the comparison
        """
        if isinstance(other, Attribute):
            return DynamicDeviceAttributeCondition(
                (self._device_id, self._attr_name),
                op,
                (other._device_id, other._attr_name),
            )
        else:
            return StaticDeviceAttributeCondition(
                self._device_id, self._attr_name, op, other
            )

    def __gt__(self, other: Any) -> AbstractCondition:
        return self._compare(other, ">")

    def __ge__(self, other: Any) -> AbstractCondition:
        return self._compare(other, ">=")

    def __lt__(self, other: Any) -> AbstractCondition:
        return self._compare(other, "<")

    def __le__(self, other: Any) -> AbstractCondition:
        return self._compare(other, "<=")

    def __eq__(self, other: Any) -> AbstractCondition:
        return self._compare(other, "=")

    def __ne__(self, other: Any) -> AbstractCondition:
        return self._compare(other, "!=")


class Command:
    """A command to be sent to a device."""

    def __init__(self, he_client: HubitatClient, device_id: int, command: str):
        self._he_client = he_client
        self._device_id = device_id
        self._command = command

    async def __call__(self, *args: Any, **_kwds: Any) -> None:
        await self._he_client.send_command(self._device_id, self._command, *args)


class Device:
    """A hubitat device."""

    def __init__(self, he_device: HubitatDevice, he_client: HubitatClient):
        self._he_device = he_device
        self._he_client = he_client

    def __getattr__(self, attr_name: str) -> Attribute | Command:
        attr = self._he_device.attribute_by_name(attr_name)
        if attr is not None:
            return Attribute(attr, self._he_device)
        cmd = self._he_device.command_by_name(attr_name)
        if cmd is not None:
            return Command(self._he_client, self._he_device.id, cmd.name)
        raise AttributeError(
            f"Attribute or command {attr_name} not found on device {self._he_device.id}"
        )


class RuleUtilities:
    """Utilities for building rules."""

    def __init__(self, engine: RuleEngine):
        self._engine = engine

    def device(self, device_id: int) -> Device:
        """Get a device by id."""
        return Device(self._he_client.get_device(device_id), self._he_client)

    def all_of(self, *conditions: AbstractCondition) -> AbstractCondition:
        """Create condition that checks if all subconditions are true."""
        return BooleanCondition(*conditions, operator="and")

    def any_of(self, *conditions: AbstractCondition) -> AbstractCondition:
        """Create condition that checks if any subcondition is true."""
        return BooleanCondition(*conditions, operator="or")

    def is_not(self, condition: AbstractCondition) -> AbstractCondition:
        """Create condition that checks if a subcondition is false."""
        return BooleanCondition(condition, operator="not")

    async def wait(self, for_time: timedelta):
        """Wait for a period of time.

        Args:
            for_time: The amount of time to wait for
        """
        await aio.sleep(for_time.total_seconds())

    async def wait_for(
        self,
        condition: AbstractCondition,
        timeout: timedelta | None = None,
        for_duration: timedelta | None = None,
    ) -> bool:
        """Wait for a condition to be true.

        Args:
            condition: The condition to wait for.
            timeout: The timeout for the condition to be true.
            for_duration: How long the condition must be true for (default is immediate)
        Returns:
            True if the condition is true after waiting, False if otherwise
        """
        if timeout is not None and for_duration is not None and timeout <= for_duration:
            raise ValueError("Timeout must be longer than duration")

        if for_duration is not None:
            condition.duration = for_duration

        return await self._wait_for_condition(condition, timeout)

    async def wait_for_change(
        self,
        attr: Attribute,
        timeout: timedelta | None = None,
    ) -> bool:
        """Wait for an attribute to change.

        Args:
            attr: The attribute to wait for.
            timeout: The timeout for the attribute to change.

        Returns:
            True if the attribute changed, False if otherwise (timeout)
        """
        condition = AttributeChangeCondition(attr._device_id, attr._attr_name)
        return await self.wait_for(condition, timeout)

    async def wait_until(self, t: time):
        """Wait until a given time.

        Args:
            t: The time to wait until.
        """
        now = datetime.now()
        target_time = datetime.combine(now.date(), t)
        if target_time < now:
            target_time = datetime.combine(now.date().replace(day=now.day + 1), t)
        wait_time = target_time - now
        await aio.sleep(wait_time.total_seconds())

    async def check(self, condition: AbstractCondition) -> bool:
        """Check if a condition is true.

        Args:
            condition: The condition to check.

        Returns:
            True if the condition is true, False otherwise
        """
        await self._engine.add_condition(condition)
        result = self._engine.get_condition_state(condition)
        self._engine.remove_condition(condition)
        return result

    async def _wait_for_condition(
        self,
        condition: AbstractCondition,
        timeout: timedelta | None = None,
    ) -> bool:
        """Internal helper to wait for a condition with optional timeout.

        Args:
            condition: The condition to wait for
            timeout: Optional timeout for the condition

        Returns:
            True if the condition was met, False if timed out
        """
        event = aio.Event()
        timeout_event = None
        if timeout is not None:
            timeout_event = aio.Event()
            condition.timeout = timeout

        await self._engine.add_condition(
            condition, condition_event=event, timeout_event=timeout_event
        )

        # Wait for the condition to become true or for timeout
        if timeout_event is not None:
            tasks = [
                aio.create_task(event.wait(), name="condition"),
                aio.create_task(timeout_event.wait(), name="timeout"),
            ]
            done, pending = await aio.wait(tasks, return_when=aio.FIRST_COMPLETED)
            # Cancel any pending tasks
            for task in pending:
                task.cancel()

            # Remove the condition from tracking
            self._engine.remove_condition(condition)

            # Check which task completed
            completed_task = done.pop()
            return completed_task.get_name() != "timeout"
        else:
            await event.wait()
            # Remove the condition from tracking
            self._engine.remove_condition(condition)
            return True


TriggerTimeProvider = Callable[[], Optional[datetime]]


class AbstractRule(abc.ABC):
    """An abstract base class for all rules."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """The unique name of the rule."""

    @property
    @abc.abstractmethod
    def description(self) -> str:
        """A description of the rule."""

    @abc.abstractmethod
    def trigger(self, utils: RuleUtilities) -> TriggerTimeProvider | AbstractCondition:
        """Trigger for the rule.

        Either returns a condition that triggers the rule when it becomes true, or a
        function that returns the next time that the rule should run.
        """

    @abc.abstractmethod
    async def run(self, utils: RuleUtilities):
        """Main logic for the rule."""
