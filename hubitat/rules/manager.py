"""
Rule management system for Hubitat automation.

This module provides the core functionality for managing and executing automation rules
in the Hubitat ecosystem. It handles:
- Rule installation and execution
- Action sequencing and control flow
- Device state monitoring and event handling
"""

import os
from datetime import timedelta
from typing import Optional

from hubitat.client import HubitatClient
from hubitat.rules.condition import (
    BooleanStateCondition,
    DeviceStateCondition,
    TimeOfDayStateCondition,
    TrueCondition,
    condition_for_model,
)
from hubitat.rules.model import (
    BooleanCondition,
    DeviceCondition,
    DeviceControlAction,
    IfThenElseAction,
    ModelAction,
    Rule,
    SceneAction,
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
from hubitat.scenes.manager import SceneManager
from util import env_var, load_models_from_json, save_models_to_json


# pylint: disable=too-few-public-methods
class _ExitAction:
    """Action that stops the execution of remaining actions."""


InternalAction = ModelAction | _ExitAction


def _find_project_root(start_path: str) -> str:
    """Find the project root by looking for app.py in parent directories.

    Args:
        start_path: The path to start searching from

    Returns:
        The path to the project root directory

    Raises:
        RuntimeError: If no project root is found
    """
    current = start_path
    while current != os.path.dirname(current):  # Stop at root directory
        if os.path.exists(os.path.join(current, "app.py")):
            return current
        current = os.path.dirname(current)
    raise RuntimeError("Could not find project root (directory containing app.py)")


class RuleManager:
    """Manages the installation and execution of automation rules.

    This class handles the lifecycle of rules, from installation through execution,
    including condition monitoring and action sequencing.
    """

    def __init__(
        self,
        he_client: HubitatClient,
        rpm: RuleProcessManager,
        scene_manager: SceneManager,
    ):
        self._process = rpm
        self._he_client = he_client
        self._scene_manager = scene_manager
        # Track installed rules by name -> (rule, condition)
        self._installed_rules: dict[str, tuple[Rule, Condition]] = {}
        rules_file = env_var("RULES_FILE", allow_null=True)
        if rules_file is None:
            project_root = _find_project_root(os.path.dirname(__file__))
            rules_file = os.path.join(project_root, "rules.json")
        self._rules_file = rules_file

    async def _save_rules(self):
        """Save all installed rules to the rules file."""
        rules = [rule for rule, _ in self._installed_rules.values()]
        await save_models_to_json(rules, self._rules_file)

    async def install_saved_rules(self):
        """Load and install all rules from the rules file."""
        rules = await load_models_from_json(Rule, self._rules_file)
        for rule in rules:
            try:
                await self.install_rule(rule)
            except Exception as e:
                print(f"Error installing rule '{rule.name}': {e}")

    async def install_rule(self, rule: Rule):
        """Install a rule into the process manager.

        Args:
            rule: The rule to install
        """
        if rule.name in self._installed_rules:
            raise ValueError(f"Rule with name '{rule.name}' is already installed")

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

        self._installed_rules[rule.name] = (rule, condition)
        await self._save_rules()

    async def uninstall_rule(self, rule_name: str):
        """Uninstall a rule by its name.

        Args:
            rule_name: The name of the rule to uninstall
        """
        if rule_name not in self._installed_rules:
            return

        _, condition = self._installed_rules[rule_name]
        await self._process.remove_condition(condition)
        del self._installed_rules[rule_name]
        await self._save_rules()

    def get_installed_rules(self) -> list[Rule]:
        """Get all currently installed rules.

        Returns:
            A list of all currently installed rules
        """
        return [rule for rule, _ in self._installed_rules.values()]

    def get_rule_by_name(self, rule_name: str) -> Rule | None:
        """Get a rule by its name.

        Args:
            rule_name: The name of the rule to get
        """
        return (
            self._installed_rules.get(rule_name)[0]
            if rule_name in self._installed_rules
            else None
        )

    async def invoke_actions(
        self, actions: list[InternalAction], rule_trigger: Optional[Condition] = None
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
            case SceneAction() as scene_action:
                await self._handle_scene(scene_action, remaining_actions, rule_trigger)
            case UntilAction() as until_action:
                await self._handle_until(until_action, remaining_actions, rule_trigger)
            case WaitAction() as wait_action:
                await self._handle_wait(wait_action, remaining_actions, rule_trigger)
            case _ExitAction():
                if rule_trigger is not None:
                    await self._process.add_condition(rule_trigger)
            case _:
                raise NotImplementedError(f"Unsupported action type: {type(action)}")

    def _on_rule_triggered(self, rule: Rule, trigger: Condition) -> Action:
        async def action(cm: ConditionManager):
            await cm.remove_condition(trigger)
            await self.invoke_actions(rule.actions + [_ExitAction()], trigger)

        return action

    def _on_condition_triggered(
        self,
        condition: Condition,
        remaining_actions: list[InternalAction],
        rule_trigger: Condition,
    ) -> Action:
        async def inner(cm: ConditionManager):
            await cm.remove_condition(condition)
            await self.invoke_actions(remaining_actions, rule_trigger)

        return inner

    def _on_condition_timeout(
        self,
        condition: Condition,
        remaining_actions: list[InternalAction],
        rule_trigger: Condition,
        exit_on_timeout: bool = False,
    ) -> Action:
        async def inner(cm: ConditionManager):
            await cm.remove_condition(condition)
            if not exit_on_timeout:
                await self.invoke_actions(remaining_actions, rule_trigger)
            else:
                await self.invoke_actions([_ExitAction()], rule_trigger)

        return inner

    async def _handle_device_control(
        self,
        action: DeviceControlAction,
        remaining_actions: list[InternalAction],
        rule_trigger: Condition,
    ):
        """Handle a device control action."""
        await self._he_client.send_command(
            action.device_id,
            action.command,
            action.arguments,
        )
        await self.invoke_actions(remaining_actions, rule_trigger)

    async def _handle_if_then_else(
        self,
        action: IfThenElseAction,
        remaining_actions: list[InternalAction],
        rule_trigger: Condition,
    ):
        """Handle an if-then-else action."""
        condition = condition_for_model(action.if_condition)

        # Add the condition to the process manager, get state, then remove it
        await self._process.add_condition(condition)
        state = self._process.check_condition_state(condition)
        await self._process.remove_condition(condition)

        if state:
            await self.invoke_actions(
                action.then_actions + remaining_actions, rule_trigger
            )
        elif action.else_actions is not None:
            await self.invoke_actions(
                action.else_actions + remaining_actions, rule_trigger
            )
        else:
            await self.invoke_actions(remaining_actions, rule_trigger)

    async def _handle_scene(
        self,
        action: SceneAction,
        remaining_actions: list[InternalAction],
        rule_trigger: Condition,
    ):
        """Handle a scene action."""
        await self._scene_manager.set_scene(action.scene_name)
        await self.invoke_actions(remaining_actions, rule_trigger)

    async def _handle_until(
        self,
        action: UntilAction,
        remaining_actions: list[InternalAction],
        rule_trigger: Condition,
    ):
        """Handle an until action."""
        timeout = (
            timedelta(seconds=action.timeout) if action.timeout is not None else None
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
        rule_trigger: Condition,
    ):
        """Handle a wait action."""
        timeout = (
            timedelta(seconds=action.timeout) if action.timeout is not None else None
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
