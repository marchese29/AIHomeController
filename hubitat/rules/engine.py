import abc
import asyncio as aio
from collections import deque
from datetime import time, timedelta
from typing import Any, Awaitable, Callable, Optional

from hubitat.client import DeviceEvent, HubitatClient
from utilities.timers import TimerService

DeviceAttribute = tuple[int, str]
AttributeState = tuple[str, Any]


class EngineCondition(abc.ABC):
    @property
    @abc.abstractmethod
    def identifier(self) -> str:
        """Unique identifier for the condition."""

    @property
    def conditions(self) -> list["EngineCondition"]:
        """Subconditions of the condition."""
        return []

    @property
    def device_attributes(self) -> list[DeviceAttribute]:
        """Device attributes this condition depends on."""
        return []

    @property
    def timeout(self) -> Optional[timedelta]:
        """Timeout for the condition."""
        return None

    @property
    def duration(self) -> Optional[timedelta]:
        """Duration for the condition."""
        return None

    def on_device_event(self, event: DeviceEvent):
        """Handles a device event."""

    def on_condition_event(self, condition: "EngineCondition", triggered: bool):
        """Handles a condition event."""

    @abc.abstractmethod
    def initialize(
        self, attrs: dict[int, dict[str, Any]], conditions: dict[str, bool]
    ) -> bool:
        """Initializes the condition."""

    @abc.abstractmethod
    def evaluate(self) -> bool:
        """Evaluates if the condition is met currently."""


class ConditionNotifier:
    """Notifier for conditions."""

    def __init__(
        self,
        condition: EngineCondition,
        event: aio.Event | None = None,
        to_event: aio.Event | None = None,
    ):
        self._condition = condition
        self._event = event
        self._to_event = to_event

    @property
    def condition(self) -> EngineCondition:
        """Condition that triggered the event."""
        return self._condition

    def notify(self):
        """Notifies the condition."""
        if self._event is not None:
            self._event.set()

    def notify_timeout(self):
        """Notifies the condition of a timeout."""
        if self._to_event is not None:
            self._to_event.set()


class RuleEngine:
    """Engine for running rules."""

    def __init__(self, he_client: HubitatClient, timer_service: TimerService):
        self._he_client = he_client
        self._timer_service = timer_service

        # DeviceId -> #(attributeName -> set[ConditionId])
        self._tracked_devices: dict[int, dict[str, set[str]]] = {}

        # ConditionId -> Condition
        self._conditions: dict[str, tuple[ConditionNotifier, bool]] = {}
        self._condition_deps: dict[str, set[str]] = {}

        # DeviceId -> #(attributeName -> attributeValue)
        self._latest_attributes: dict[int, dict[str, Any]] = {}

        # Protects the integrity of device tracking and condition state
        self._engine_lock = aio.Lock()

    ####################
    # PUBLIC INTERFACE #
    ####################

    async def add_condition(
        self,
        condition: EngineCondition,
        condition_event: aio.Event | None = None,
        timeout_event: aio.Event | None = None,
    ):
        async with self._engine_lock:
            await self._add_condition(
                ConditionNotifier(condition, condition_event, timeout_event)
            )

    async def remove_condition(self, condition: EngineCondition):
        async with self._engine_lock:
            self._remove_condition(condition)

    def get_condition_state(self, condition: EngineCondition) -> bool:
        return self._conditions[condition.identifier][1]

    def get_attribute_value(self, device_id: int, attr_name: str) -> Any:
        return self._latest_attributes[device_id][attr_name]

    ############
    # REACTORS #
    ############

    async def _on_device_event(self, event: DeviceEvent):
        device_id = int(event.device_id)
        attr = event.attribute

        # Update the state of our device tracking
        self._latest_attributes[device_id][attr] = event.value

        # Notify conditions impacted directly by the device state change
        impacted = [
            self._conditions[cid][0] for cid in self._tracked_devices[device_id][attr]
        ]
        for notifier in impacted:
            notifier.condition.on_device_event(event)

        await self._process_condition_change(impacted)

    def _on_condition_timeout(
        self, notifier: ConditionNotifier
    ) -> Callable[[str], Awaitable[None]]:
        """Handles a condition timeout"""

        async def _on_timeout(_timer_id: str):
            # We timed out, so stop waiting for the condition to become true
            await self.remove_condition(notifier.condition)
            notifier.notify_timeout()

        return _on_timeout

    #################
    # STATE UPDATES #
    #################

    def _propagate_state_update(
        self, notifiers: list[ConditionNotifier]
    ) -> list[ConditionNotifier]:
        """Propagates the state update to any dependent conditions

        Returns:
            List of conditions that were impacted by the state update
        """

        # We aren't de-duping on a visited set since we need all edges traversed
        work = deque(notifiers)
        touched_conditions: set[str] = set()
        while len(work) > 0:
            current = work.popleft()
            current_id = current.condition.identifier
            touched_conditions.add(current_id)
            current_state = self._conditions[current_id][1]
            new_state = current.condition.evaluate()

            # Update our tracking state if it has changed
            if new_state != current_state:
                self._conditions[current_id] = (current, new_state)

            # Process dependencies
            if current_id in self._condition_deps:
                for dep_cond_id in self._condition_deps[current_id]:
                    dep_cond = self._conditions[dep_cond_id][0].condition
                    dep_cond.on_condition_event(current.condition, new_state)
                    work.append(dep_cond)

        return [self._conditions[cid][0] for cid in touched_conditions]

    async def _process_condition_change(self, impacted: list[ConditionNotifier]):
        """Processes a condition change"""
        # Get a snapshot of our existing state so we can see what changed
        previous_state = {
            cid: self._conditions[cid][1] for cid in self._conditions.keys()
        }

        # Propagate the state change to transitively impacted conditions
        notifiers = self._propagate_state_update(impacted)

        for notifier in notifiers:
            curr = self._conditions[notifier.condition.identifier][1]
            prev = previous_state[notifier.condition.identifier]

            # When a condition becomes false, cancel the duration timer if it exists
            if (
                prev is True
                and curr is False
                and notifier.condition.duration is not None
            ):
                self._timer_service.cancel_timer(
                    f"condition_duration({notifier.condition.identifier})"
                )

            # When a condtion with a duration becomes true, notify the event after the
            # condition remains true for the entire duration
            if (
                curr is True
                and prev is False
                and notifier.condition.duration is not None
            ):

                def _notify_duration():
                    # When the duration timer expires remove the condition, cancel the
                    # timeout timer, and notify the event
                    self.remove_condition(notifier.condition)
                    self._timer_service.cancel_timer(
                        f"condition_timeout({notifier.condition.identifier})"
                    )
                    notifier.notify()

                self._timer_service.start_timer(
                    f"condition_duration({notifier.condition.identifier})",
                    notifier.condition.duration,
                    _notify_duration,
                )
                return

            # When a condition becomes true, cancel the timeout timer if it exists then
            # notify the event
            if curr is True and prev is False:
                self.remove_condition(notifier.condition)
                self._timer_service.cancel_timer(
                    f"condition_timeout({notifier.condition.identifier})"
                )
                notifier.notify()

    ############
    # TRACKING #
    ############

    async def _add_condition(self, notifier: ConditionNotifier):
        # Add device to tracking
        new_device_attrs = self._track_device_attributes(notifier.condition)
        if len(new_device_attrs) > 0:
            await self._fetch_new_attributes(new_device_attrs)

        # Initialize the subconditions
        init_cond_states = await self._initialize_sub_conditions(notifier.condition)

        # Initialize the condition
        init_attrs: dict[int, dict[str, Any]] = {}
        for device_attr in notifier.condition.device_attributes:
            (device_id, attr_name) = device_attr
            init_attrs[device_id][attr_name] = self._latest_attributes[device_id][
                attr_name
            ]
        state = notifier.condition.initialize(init_attrs, init_cond_states)
        self._conditions[notifier.condition.identifier] = (notifier, state)

        # Subscribe to any relevant device events
        for device_attr in notifier.condition.device_attributes:
            (device_id, attr_name) = device_attr
            self._he_client.subscribe(device_id, [attr_name], self._on_device_event)

        # Start timeout timer if condition has a timeout
        if notifier.condition.timeout is not None:
            await self._timer_service.start_timer(
                f"condition_timeout({notifier.condition.identifier})",
                notifier.condition.timeout,
                self._on_condition_timeout(notifier),
            )

        # Start duration timer if condition is already true
        if state is True and notifier.condition.duration is not None:
            await self._timer_service.start_timer(
                f"condition_duration({notifier.condition.identifier})",
                notifier.condition.duration,
                lambda _: notifier.notify(),
            )

        # TODO: Durations and Time-of-day

    def _remove_condition(self, condition: EngineCondition):
        # Cancel timeout timer if it exists
        self._timer_service.cancel_timer(f"condition_timeout({condition.identifier})")
        self._timer_service.cancel_timer(f"condition_duration({condition.identifier})")

        # Remove condition from tracking
        if condition.identifier in self._conditions:
            del self._conditions[condition.identifier]

            # Remove condition from device tracking
            for device_attr in condition.device_attributes:
                device_id, attr_name = device_attr
                self._tracked_devices[device_id][attr_name].discard(
                    condition.identifier
                )
                # If no more conditions care about this attribute
                if len(self._tracked_devices[device_id][attr_name]) == 0:
                    # Unsubscribe from this attribute
                    del self._tracked_devices[device_id][attr_name]
                    del self._latest_attributes[device_id][attr_name]
                    if len(self._tracked_devices[device_id]) == 0:
                        # No more attributes to track, unsubscribe from all events
                        self._he_client.unsubscribe(device_id)
                        del self._tracked_devices[device_id]
                    if len(self._latest_attributes[device_id]) == 0:
                        del self._latest_attributes[device_id]

            # Recursively remove conditions from dependencies
            if condition.identifier in self._condition_deps:
                del self._condition_deps[condition.identifier]
            for sub_condition in condition.conditions:
                if sub_condition.identifier in self._conditions:
                    self._remove_condition(sub_condition)

    ##################
    # INITIALIZATION #
    ##################

    def _track_device_attributes(
        self, condition: EngineCondition
    ) -> list[DeviceAttribute]:
        new_device_attrs: list[DeviceAttribute] = []
        for device_attr in condition.device_attributes:
            (device_id, attr_name) = device_attr
            if device_id not in self._tracked_devices:
                self._tracked_devices[device_id] = {}
            if attr_name not in self._tracked_devices[device_id]:
                self._tracked_devices[device_id][attr_name] = set()
            self._tracked_devices[device_id][attr_name].add(condition.identifier)
            new_device_attrs.append((device_id, attr_name))
        return new_device_attrs

    async def _fetch_new_attributes(self, device_attrs: list[DeviceAttribute]):
        for device_id, attr_name in device_attrs:
            if device_id not in self._latest_attributes:
                self._latest_attributes[device_id] = {}
            self._latest_attributes[device_id][
                attr_name
            ] = await self._he_client.get_attribute(device_id, attr_name)

    async def _initialize_sub_conditions(
        self, condition: EngineCondition
    ) -> dict[str, bool]:
        init_cond_states: dict[str, bool] = {}
        for sub_condition in condition.conditions:
            if sub_condition.identifier not in self._conditions:
                if sub_condition.identifier not in self._condition_deps:
                    self._condition_deps[sub_condition.identifier] = set()
                self._condition_deps[sub_condition.identifier].add(condition.identifier)
                await self._add_condition(ConditionNotifier(sub_condition))  # RECURSION
            init_cond_states[sub_condition.identifier] = self._conditions[
                sub_condition.identifier
            ][1]
        return init_cond_states
