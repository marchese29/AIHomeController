from datetime import datetime, time, timedelta
from typing import Optional, override

from hubitat.client import DeviceEvent
from hubitat.rules.model import (
    BooleanCondition,
    DeviceCondition,
    StateCondition,
    TimeOfDayCondition,
)
from hubitat.rules.process import Condition, DeviceState

def _condition_identifier(condition: StateCondition) -> str:
    """Generate a human-readable identifier for a condition.
    
    Args:
        condition: The condition to generate an identifier for
        
    Returns:
        A string identifier representing the condition's logic
    """
    match condition:
        case DeviceCondition() as device_condition:
            return (
                f"hubitat({device_condition.device_id}-{device_condition.attribute} "
                f"{device_condition.operator} {device_condition.value})"
            )
        case BooleanCondition() as bool_condition:
            return f' {bool_condition.operator} '.join(
                [f'({_condition_identifier(c)})' for c in bool_condition.conditions]
            )
        case TimeOfDayCondition() as time_condition:
            return f"time_of_day({time_condition.operator} {time_condition.hour:02d}:{time_condition.minute:02d})"
        case _:
            raise ValueError(f"Unknown condition type: {type(condition)}")


def condition_for_model(condition: StateCondition, timeout: Optional[timedelta] = None) -> Condition:
    """Create a Condition instance from a model condition.
    
    Args:
        condition: The model condition to convert
        on_trigger: Optional action to execute when the condition is triggered
        delete_on_trigger: Whether to remove the condition after triggering
        
    Returns:
        A Condition instance appropriate for the model type
    """
    match condition:
        case DeviceCondition() as device_condition:
            return DeviceStateCondition(device_condition, timeout)
        case BooleanCondition() as bool_condition:
            return BooleanStateCondition(bool_condition, timeout)
        case _:
            raise ValueError(f"Unknown condition type: {type(condition)}")


class DeviceStateCondition(Condition):
    """Condition that evaluates based on a device's attribute value.
    
    This condition monitors a specific device attribute and evaluates to true
    when the attribute matches the specified operator and value.
    """
    
    _instance_counter = 0
    
    def __init__(self, model: DeviceCondition, timeout: Optional[timedelta] = None):
        self._model = model
        self._previous_value = None
        self._device_value = None
        self._value_type = type(model.value)
        self._timeout = timeout
        self._instance_number = DeviceStateCondition._instance_counter
        DeviceStateCondition._instance_counter += 1

    @property
    @override
    def identifier(self) -> str:
        base_id = _condition_identifier(self._model)
        return f"{base_id}#{self._instance_number}"

    @property
    @override
    def devices(self) -> dict[int, set[str]]:
        return {self._model.device_id: {self._model.attribute}}

    @property
    @override
    def duration(self) -> Optional[int]:
        """The duration (in seconds) that this condition must remain true before triggering actions."""
        return self._model.duration
    
    @property
    @override
    def timeout(self) -> Optional[timedelta]:
        """The timeout for this condition."""
        return self._timeout

    @override
    def initialize(self, attrs: dict[int, DeviceState], conditions: dict[str, bool]) -> bool:
        self._device_value = self._cast_value(attrs[self._model.device_id][self._model.attribute])
        self._previous_value = self._device_value
        return self.evaluate()

    @override
    def on_device_event(self, event: DeviceEvent):
        self._previous_value = self._device_value
        self._device_value = self._cast_value(event.value)

    def _cast_value(self, value: any) -> any:
        """Cast the incoming value to match the model value type.
        
        Args:
            value: The value to cast
            
        Returns:
            The value cast to the appropriate type
        """
        if value is None:
            return None
            
        try:
            if self._value_type == bool:
                if isinstance(value, str):
                    return value.lower() in ('true', '1', 'yes', 'on', 'active', 'open')
                return bool(value)
            elif self._value_type == int:
                return int(value)
            elif self._value_type == float:
                return float(value)
            elif self._value_type == str:
                return str(value)
            return value
        except (ValueError, TypeError):
            return value

    @override
    def evaluate(self) -> bool:
        match self._model.operator:
            case "=":
                return self._device_value == self._model.value
            case "!=":
                return self._device_value != self._model.value
            case ">":
                return self._device_value > self._model.value
            case ">=":
                return self._device_value >= self._model.value
            case "<":
                return self._device_value < self._model.value
            case "<=":
                return self._device_value <= self._model.value
            case "changed":
                return self._previous_value != self._device_value
            case _:
                raise ValueError(f"Unknown operator: {self._model.operator}")


class BooleanStateCondition(Condition):
    """Condition that combines multiple subconditions with boolean logic.
    
    This condition evaluates multiple subconditions and combines their results
    using AND or OR operators.
    """
    
    _instance_counter = 0
    
    def __init__(self, model: BooleanCondition, timeout: Optional[timedelta] = None):
        self._model = model
        self._subconditions: dict[str, tuple[Condition, bool]] = {}
        for subcondition in model.conditions:
            condition = condition_for_model(subcondition)
            self._subconditions[condition.identifier] = (condition, False)
        if model.operator == 'not' and len(self._subconditions) != 1:
            raise ValueError("Boolean operator 'not' requires exactly one subcondition")
        self._timeout = timeout
        self._instance_number = BooleanStateCondition._instance_counter
        BooleanStateCondition._instance_counter += 1

    @property
    @override
    def identifier(self) -> str:
        base_id = _condition_identifier(self._model)
        return f"{base_id}#{self._instance_number}"

    @property
    @override
    def conditions(self) -> list[Condition]:
        return [c for (c, _) in self._subconditions.values()]

    @property
    @override
    def duration(self) -> Optional[int]:
        """The duration (in seconds) that this condition must remain true before triggering actions."""
        return self._model.duration
    
    @property
    @override
    def timeout(self) -> Optional[timedelta]:
        """The timeout for this condition."""
        return self._timeout

    @override
    def initialize(self, attrs: dict[int, DeviceState], conditions: dict[str, bool]) -> bool:
        for (condition_id, state) in conditions.items():
            self._subconditions[condition_id] = (self._subconditions[condition_id][0], state)
        return self.evaluate()

    @override
    def evaluate(self) -> bool:
        match self._model.operator:
            case "and":
                return all([state for (_, state) in self._subconditions.values()])
            case "or":
                return any([state for (_, state) in self._subconditions.values()])
            case "not":
                return not [state for (_, state) in self._subconditions.values()][0]
            case _:
                raise ValueError(f"Unknown operator: {self._model.operator}")


class TimeOfDayStateCondition(Condition):
    """Condition that evaluates based on the current time of day.
    
    This condition evaluates to true if the current time matches any of the specified times.
    """

    _instance_counter = 0
    
    def __init__(self, model: TimeOfDayCondition):
        self._model = model
        # TODO: Timezone bullshit
        self._check_times = [time(hour=model.hour, minute=model.minute)]
        # For the 'is' operator, we re-trigger a minute later also so the condition can become false again
        if model.operator == 'is':
            self._check_times.append(time(hour=model.hour, minute=model.minute) + timedelta(minutes=1))
        self._instance_number = TimeOfDayStateCondition._instance_counter
        TimeOfDayStateCondition._instance_counter += 1

    @property
    @override
    def identifier(self) -> str:
        base_id = _condition_identifier(self._model)
        return f"{base_id}#{self._instance_number}"
    
    @property
    @override
    def check_times(self) -> Optional[list[time]]:
        return self._check_times

    @override
    def evaluate(self) -> bool:
        model_time = time(hour=self._model.hour, minute=self._model.minute)
        now = datetime.now().replace(second=0, microsecond=0).time()
        match self._model.operator:
            case 'is':
                return now == model_time
            case 'before':
                return now < model_time
            case 'after':
                return now >= model_time
            case _:
                raise ValueError(f"Unknown operator: {self._model.operator}")
