"""
Rule management system for Hubitat automation.

This module provides the core functionality for managing and executing automation rules
in the Hubitat ecosystem. It handles:
- Rule installation and execution
- Action sequencing and control flow
- Device state monitoring and event handling
"""

from datetime import timedelta

from hubitat.client import HubitatClient
from hubitat.rules.condition import (
    BooleanStateCondition,
    condition_for_model,
    DeviceStateCondition,
    TimeOfDayStateCondition,
    TrueCondition,
)
from hubitat.rules.model import (
    BooleanCondition,
    DeviceCondition,
    DeviceControlAction,
    IfThenElseAction,
    ModelAction,
    Rule,
    TimeOfDayCondition,
    UntilAction,
    WaitAction,
)
from hubitat.rules.process import (
    Action,
    Condition,
    ConditionManager,
    RuleProcessManager,
)


class _ExitAction:
    """Action that stops the execution of remaining actions."""
    pass


InternalAction = ModelAction | _ExitAction


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
                condition = DeviceStateCondition(trigger)
                on_trigger = self._on_rule_triggered(rule, condition)
                condition.action = on_trigger
                await self._process.add_condition(condition)
            case BooleanCondition() as trigger:
                condition = BooleanStateCondition(trigger)
                on_trigger = self._on_rule_triggered(rule, condition)
                condition.action = on_trigger                
                await self._process.add_condition(condition)
            case TimeOfDayCondition() as trigger:
                condition = TimeOfDayStateCondition(trigger)
                on_trigger = self._on_rule_triggered(rule, condition)
                condition.action = on_trigger
                await self._process.add_condition(condition)
            case _:
                raise ValueError(f"Unknown trigger type: {type(rule.trigger)}")
    
    def _on_rule_triggered(self, rule: Rule, trigger: Condition) -> Action:
        async def action(cm: ConditionManager):
            cm.remove_condition(trigger)
            await self._invoke_actions(rule.actions + [_ExitAction()], trigger)
        return action
    
    def _on_condition_triggered(
        self,
        condition: Condition,
        remaining_actions: list[InternalAction],
        rule_trigger: Condition
    ) -> Action:
        async def inner(cm: ConditionManager):
            cm.remove_condition(condition)
            await self._invoke_actions(remaining_actions, rule_trigger)
        return inner

    def _on_condition_timeout(
        self,
        condition: Condition,
        remaining_actions: list[InternalAction],
        rule_trigger: Condition,
        exit_on_timeout: bool = False
    ) -> Action:
        async def inner(cm: ConditionManager):
            cm.remove_condition(condition)
            if not exit_on_timeout:
                await self._invoke_actions(remaining_actions, rule_trigger)
            else:
                await self._invoke_actions([_ExitAction()], rule_trigger)
        return inner

    async def _invoke_actions(
        self, 
        actions: list[InternalAction], 
        rule_trigger: Condition
    ):
        """Execute a sequence of actions.
        
        This method processes a list of actions sequentially. For each action, it 
        delegates to the appropriate handler method based on the action type. The 
        handler methods determine whether to continue executing remaining actions 
        immediately or wait for some condition.
        
        Args:
            actions: The list of actions to execute
        """
        if not actions:
            return
            
        action = actions[0]
        remaining_actions = actions[1:]
        match action:
            case DeviceControlAction() as device_action:
                await self._handle_device_control(
                    device_action, remaining_actions, rule_trigger
                )
            case IfThenElseAction() as if_else_action:
                await self._handle_if_then_else(
                    if_else_action, remaining_actions, rule_trigger
                )
            case UntilAction() as until_action:
                await self._handle_until(
                    until_action, remaining_actions, rule_trigger
                )
            case WaitAction() as wait_action:
                await self._handle_wait(
                    wait_action, remaining_actions, rule_trigger
                )
            case _ExitAction():
                await self._process.add_condition(rule_trigger)
            case _:
                raise NotImplementedError(
                    f"Unsupported action type: {type(action)}"
                )

    async def _handle_device_control(
        self, 
        action: DeviceControlAction, 
        remaining_actions: list[InternalAction], 
        rule_trigger: Condition
    ):
        """Handle a device control action."""
        await self._he_client.send_command(
            action.device_id,
            action.command,
            action.arguments,
        )
        await self._invoke_actions(remaining_actions, rule_trigger)

    async def _handle_if_then_else(
        self, 
        action: IfThenElseAction, 
        remaining_actions: list[InternalAction], 
        rule_trigger: Condition
    ):
        """Handle an if-then-else action."""
        condition = condition_for_model(action.if_condition)
        
        # Add the condition to the process manager, get state, then remove it
        await self._process.add_condition(condition)
        state = self._process.check_condition_state(condition)
        self._process.remove_condition(condition)

        if state:
            await self._invoke_actions(
                action.then_actions + remaining_actions, rule_trigger
            )
        elif action.else_actions is not None:
            await self._invoke_actions(
                action.else_actions + remaining_actions, rule_trigger
            )
        else:
            await self._invoke_actions(remaining_actions, rule_trigger)

    async def _handle_until(
        self, 
        action: UntilAction, 
        remaining_actions: list[InternalAction], 
        rule_trigger: Condition
    ):
        """Handle an until action."""
        timeout = (
            timedelta(seconds=action.timeout) 
            if action.timeout is not None 
            else None
        )
        condition = condition_for_model(action.condition, timeout)
        condition.action = self._on_condition_triggered(
            condition, action.until_actions + remaining_actions, rule_trigger
        )
        condition.timeout_action = self._on_condition_timeout(
            condition, action.timeout_actions + remaining_actions, rule_trigger
        )
        await self._process.add_condition(condition)

    async def _handle_wait(
        self, 
        action: WaitAction, 
        remaining_actions: list[InternalAction], 
        rule_trigger: Condition
    ):
        """Handle a wait action."""
        timeout = (
            timedelta(seconds=action.timeout) 
            if action.timeout is not None 
            else None
        )
        if action.condition is None:
            condition = TrueCondition(timeout)
        else:
            condition = condition_for_model(action.condition, timeout)
        condition.action = self._on_condition_triggered(
            condition, remaining_actions, rule_trigger
        )
        condition.timeout_action = self._on_condition_timeout(
            condition, remaining_actions, rule_trigger, action.end_on_timeout
        )
        await self._process.add_condition(condition)
