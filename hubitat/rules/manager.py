"""
Rule management system for Hubitat automation.

This module provides the core functionality for managing and executing automation rules
in the Hubitat ecosystem. It handles:
- Condition evaluation (device states and boolean combinations)
- Rule installation and execution
- Action sequencing and control flow
- Device state monitoring and event handling
"""

from typing import Optional, override

from hubitat.client import HubitatClient, DeviceEvent
from hubitat.rules.model import (BooleanCondition, DeviceCondition,
                               DeviceControlAction, IfThenElseAction, Rule,
                               StateCondition, UntilAction, WaitAction)
from hubitat.rules.process import Action, Condition, DeviceState, RuleProcessManager, ConditionManager


def _condition_identifier(condition: StateCondition) -> str:
    """Generate a human-readable identifier for a condition.
    
    Args:
        condition: The condition to generate an identifier for
        
    Returns:
        A string identifier representing the condition's logic
    """
    match condition:
        case DeviceCondition() as device_condition:
            return (f"hubitat({device_condition.device_id}-{device_condition.attribute}) "
                   f"{device_condition.operator} {device_condition.value}")
        case BooleanCondition() as bool_condition:
            return f' {bool_condition.operator} '.join(
                [f'({_condition_identifier(c)})' for c in bool_condition.conditions])
        case _:
            raise ValueError(f"Unknown condition type: {type(condition)}")


def _condition_for_model(
        condition: StateCondition,
        on_trigger: Optional[Action] = None,
        delete_on_trigger: bool = False) -> Condition:
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
            return _DeviceCondition(device_condition, on_trigger, delete_on_trigger)
        case BooleanCondition() as bool_condition:
            return _BooleanCondition(bool_condition, on_trigger, delete_on_trigger)
        case _:
            raise ValueError(f"Unknown condition type: {type(condition)}")


class _DeviceCondition(Condition):
    """Condition that evaluates based on a device's attribute value.
    
    This condition monitors a specific device attribute and evaluates to true
    when the attribute matches the specified operator and value.
    """
    
    def __init__(self, model: DeviceCondition, on_trigger: Optional[Action] = None, delete_on_trigger: bool = False):
        self._model = model
        self._on_trigger = on_trigger
        self._delete_on_trigger = delete_on_trigger
        self._device_value = None
        self._value_type = type(model.value)

    @property
    @override
    def identifier(self) -> str:
        return _condition_identifier(self._model)

    @property
    @override
    def devices(self) -> dict[int, set[str]]:
        return {self._model.device_id: {self._model.attribute}}

    @property
    @override
    def action(self) -> Optional[Action]:
        async def on_trigger(cm: ConditionManager):
            if self._on_trigger is not None:
                await self._on_trigger(cm)
            if self._delete_on_trigger:
                cm.remove_condition(self)
        return on_trigger

    @override
    def initialize(self, attrs: dict[int, DeviceState], conditions: dict[str, bool]) -> bool:
        self._device_value = self._cast_value(attrs[self._model.device_id][self._model.attribute])
        return self.evaluate()

    @override
    def on_device_event(self, event: DeviceEvent):
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
                    return value.lower() in ('true', '1', 'yes', 'on')
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
            case "==":
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
            case _:
                raise ValueError(f"Unknown operator: {self._model.operator}")


class _BooleanCondition(Condition):
    """Condition that combines multiple subconditions with boolean logic.
    
    This condition evaluates multiple subconditions and combines their results
    using AND or OR operators.
    """
    
    def __init__(self, model: BooleanCondition, on_trigger: Optional[Action] = None, delete_on_trigger: bool = False):
        self._model = model
        self._subconditions: dict[str, tuple[Condition, bool]] = {}
        for subcondition in model.conditions:
            condition = _condition_for_model(subcondition)
            self._subconditions[condition.identifier] = (condition, False)
        self._on_trigger = on_trigger
        self._delete_on_trigger = delete_on_trigger

    @property
    @override
    def identifier(self) -> str:
        return _condition_identifier(self._model)

    @property
    @override
    def conditions(self) -> list[Condition]:
        return [c for (c, _) in self._subconditions.values()]

    @property
    @override
    def action(self) -> Optional[Action]:
        async def on_trigger(cm: ConditionManager):
            if self._on_trigger is not None:
                await self._on_trigger(cm)
            if self._delete_on_trigger:
                cm.remove_condition(self)
        return on_trigger

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
            case _:
                raise ValueError(f"Unknown operator: {self._model.operator}")


class RuleManager:
    """Manages the installation and execution of automation rules.
    
    This class handles the lifecycle of rules, from installation through execution,
    including condition monitoring and action sequencing.
    """
    
    def __init__(self, he_client: HubitatClient):
        self._process = RuleProcessManager(he_client)
        self._he_client = he_client

    async def install_rule(self, rule: Rule):
        """Install a rule into the process manager.
        
        Args:
            rule: The rule to install
        """
        match rule.trigger:
            case DeviceCondition() as trigger:
                async def on_action(_cm: ConditionManager):
                    await self._invoke_actions(rule.actions)
                await self._process.add_condition(_DeviceCondition(trigger, on_action))
            case BooleanCondition() as trigger:
                async def on_action(_cm: ConditionManager):
                    await self._invoke_actions(rule.actions)
                await self._process.add_condition(_BooleanCondition(trigger, on_action))
            case _:
                raise ValueError(f"Unknown trigger type: {type(rule.trigger)}")

    async def _invoke_actions(self, actions: list[Action]):
        """Execute a sequence of actions until a blocking action is encountered.
        
        Args:
            actions: The list of actions to execute
        """
        for i in range(len(actions)):
            if await self._invoke_action(actions[i], actions[i+1:]):
                break

    async def _invoke_action(self, action: Action, remaining_actions: list[Action]) -> bool:
        """Execute a single action and return whether it blocks subsequent actions.
        
        Args:
            action: The action to execute
            remaining_actions: Actions that would follow this one
            
        Returns:
            True if the action blocks subsequent actions, False otherwise
        """
        match action:
            case DeviceControlAction() as device_action:
                await self._he_client.send_command(
                    device_action.device_id,
                    device_action.command,
                    device_action.arguments
                )
                return False

            case IfThenElseAction() as if_else_action:
                condition = _condition_for_model(if_else_action.if_condition, delete_on_trigger=True)
                await self._process.add_condition(condition)
                state = self._process.check_condition_state(condition)

                if state:
                    await self._invoke_actions(if_else_action.then_actions)
                elif if_else_action.else_actions is not None:
                    await self._invoke_actions(if_else_action.else_actions)
                return False

            case UntilAction() as until_action:
                async def on_trigger(_cm: ConditionManager):
                    await self._invoke_actions(until_action.until_actions)

                condition = _condition_for_model(until_action.condition, on_trigger, delete_on_trigger=True)
                await self._process.add_condition(condition)
                return True

            case WaitAction() as wait_action:
                async def on_trigger(_cm: ConditionManager):
                    await self._invoke_actions(remaining_actions)

                condition = _condition_for_model(wait_action.condition, on_trigger, delete_on_trigger=True)
                await self._process.add_condition(condition)
                return True

            case _:
                raise NotImplementedError(f"Unsupported action type: {type(action)}")
