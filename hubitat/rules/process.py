from abc import abstractmethod, ABC
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any, Optional

from hubitat.client import HubitatClient, DeviceEvent

DeviceState = dict[str, Any]
Action = Callable[['ConditionManager'], Awaitable[None]]


class Condition(ABC):
    """Represents a single condition that can be triggered and perform custom logic."""

    @property
    @abstractmethod
    def identifier(self) -> str:
        """A unique identifier for this condition."""
        ...

    @property
    def devices(self) -> dict[int, set[str]]:
        """The list of ids forhe devices that this condition depends on."""
        return {}

    @property
    def conditions(self) -> list['Condition']:
        """The list of conditions that this condition depends on."""
        return []

    @property
    def action(self) -> Optional[Action]:
        """The action to execute when this condition is met."""
        return None

    @property
    def trigger_always(self) -> bool:
        """If true, actions will always be invoked whenever the condition remains true after its states are updated.  If
        false, actions are only carried out when state switches to true."""
        return False

    def initialize(self, attrs: dict[int, DeviceState], conditions: dict[str, bool]) -> bool:
        """Called to initialize the condition with the initial device attribute states."""
        return False

    def on_device_event(self, event: DeviceEvent):
        """Called to update the state of a dependent device"""
        pass

    def on_condition_event(self, condition: 'Condition', triggered: bool):
        """Called to report a sub-condition state update"""
        pass

    @abstractmethod
    def evaluate(self) -> bool:
        """Evaluates if the condition is currently met"""
        ...


class ConditionManager:
    """A restricted interface for condition management that only allows removing conditions."""
    
    def __init__(self, rpm: 'RuleProcessManager'):
        self._rpm = rpm
        
    def remove_condition(self, condition: 'Condition'):
        """Removes a condition from the process manager."""
        self._rpm.remove_condition(condition)


class RuleProcessManager:
    """Manages the various processes waiting for conditions to be met."""

    def __init__(self, he_client: HubitatClient):
        self._he_client = he_client

        # ConditionId -> Condition
        self._conditions: dict[str, tuple[Condition, bool]] = {}
        self._condition_deps: dict[str, set[str]] = {}

        # DeviceId -> #(attributeName -> set[ConditionId])
        self._tracked_devices: dict[int, dict[str, set[str]]] = {}
        # DeviceId -> #(attributeName -> attributeValue)
        self._latest_attributes: dict[int, DeviceState] = {}

    async def add_condition(self, condition: Condition):
        """Adds a new condition to the process manager"""
        new_device_attrs = self._track_device_attributes(condition)
        await self._fetch_new_attributes(new_device_attrs)
        init_cond_states = await self._initialize_sub_conditions(condition)
        init_attrs = self._prepare_init_attributes(condition)
        self._conditions[condition.identifier] = (condition, condition.initialize(init_attrs, init_cond_states))

        # Subscribe to any relevant device events
        for (device_id, attrs) in new_device_attrs.items():
            self._he_client.subscribe(device_id, list(attrs), self._on_device_event)

    def remove_condition(self, condition: Condition):
        """Removes a condition from the process manager"""
        # Remove condition from tracking
        if condition.identifier in self._conditions:
            del self._conditions[condition.identifier]

        # Remove condition from device tracking
        for device_id, attrs in condition.devices.items():
            for attr in attrs:
                self._tracked_devices[device_id][attr].discard(condition.identifier)
                # If no more conditions care about this attribute
                if len(self._tracked_devices[device_id][attr]) == 0:
                    # Unsubscribe from this attribute
                    self._he_client.unsubscribe(device_id, self._on_device_event)
                    del self._tracked_devices[device_id][attr]
                    del self._latest_attributes[device_id][attr]
                    if len(self._tracked_devices[device_id]) == 0:
                        del self._tracked_devices[device_id]
        
        # Recursively remove conditions from dependencies
        del self._condition_deps[condition.identifier]
        for sub_condition in condition.conditions:
            if sub_condition.identifier in self._conditions:
                self.remove_condition(sub_condition)
    
    def check_condition_state(self, condition: Condition) -> bool:
        """Checks if a condition is currently met"""
        return self._conditions[condition.identifier][1]

    def _track_device_attributes(self, condition: Condition) -> dict[int, set[str]]:
        new_device_attrs: dict[int, set[str]] = {}
        for (device_id, attrs) in condition.devices.items():
            if device_id not in self._tracked_devices:
                self._tracked_devices[device_id] = {}
                new_device_attrs[device_id] = set()
            for attr in attrs:
                if attr not in self._tracked_devices[device_id]:
                    self._tracked_devices[device_id][attr] = set()
                    new_device_attrs[device_id].add(attr)
                self._tracked_devices[device_id][attr].add(condition.identifier)
        return new_device_attrs

    async def _fetch_new_attributes(self, new_device_attrs: dict[int, set[str]]):
        for (device_id, attrs) in new_device_attrs.items():
            for attr in attrs:
                if device_id not in self._latest_attributes:
                    self._latest_attributes[device_id] = {}
                self._latest_attributes[device_id][attr] = await self._he_client.get_attribute(device_id, attr)

    async def _initialize_sub_conditions(self, condition: Condition) -> dict[str, bool]:
        init_cond_states: dict[str, bool] = {}
        for sub_condition in condition.conditions:
            if sub_condition.identifier not in self._conditions:
                if sub_condition.identifier not in self._condition_deps:
                    self._condition_deps[sub_condition.identifier] = set()
                self._condition_deps[sub_condition.identifier].add(condition.identifier)
                await self.add_condition(sub_condition)  # RECURSION
            init_cond_states[sub_condition.identifier] = self._conditions[sub_condition.identifier][1]
        return init_cond_states

    def _prepare_init_attributes(self, condition: Condition) -> dict[int, DeviceState]:
        """Prepares initialization attributes for a condition"""
        init_attrs: dict[int, DeviceState] = {}
        for (device_id, attrs) in condition.devices.items():
            init_attrs[device_id] = {}
            for attr in attrs:
                init_attrs[device_id][attr] = self._latest_attributes[device_id][attr]
        return init_attrs

    def _propagate_state_update(self, conditions: list[Condition]) -> list[Condition]:
        """Propagates the state update to any dependent conditions.  Returns triggered conditions"""

        # We are not de-duping on a visited set because we need each edge to be traversed always
        work = deque(conditions)
        touched_conditions: set[str] = set()
        while len(work) > 0:
            current = work.popleft()
            current_id = current.identifier
            touched_conditions.add(current_id)
            current_state = self._conditions[current_id][1]
            new_state = current.evaluate()

            # Update our tracking state if it has changed
            if new_state != current_state:
                self._conditions[current_id] = (current, new_state)

            # Process dependencies
            if current_id in self._condition_deps:
                for dep_cond_id in self._condition_deps[current_id]:
                    dep_cond = self._conditions[dep_cond_id][0]
                    dep_cond.on_condition_event(current, new_state)
                    work.append(dep_cond)

        return [self._conditions[cid][0] for cid in touched_conditions]

    async def _on_device_event(self, event: DeviceEvent):
        device_id = int(event.device_id)
        attr = event.attribute

        # Get a snapshot of our existing state so we can see what changed
        previous_state = {cid: self._conditions[cid][1] for cid in self._conditions.keys()}

        # Update the state of our device tracking
        self._latest_attributes[device_id][attr] = event.value

        # Notify conditions impacted directly by the device state change
        impacted = [self._conditions[cid][0] for cid in self._tracked_devices[device_id][attr]]
        for imp_condition in impacted:
            imp_condition.on_device_event(event)

        # Propagate the state change to transitively impacted conditions
        touched_conditions = self._propagate_state_update(impacted)

        # Trigger actions where appropriate
        condition_manager = ConditionManager(self)
        for condition in [c for c in touched_conditions if c.action is not None]:
            curr = self._conditions[condition.identifier][1]
            prev = previous_state[condition.identifier]
            if (curr is True and prev is False) or (curr is True and condition.trigger_always):
                await condition.action(condition_manager)
