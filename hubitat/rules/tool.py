"""Tools for managing Hubitat rules through GPT functions.

This module provides a set of GPT function tools that enable interaction with Hubitat rules
through a natural language interface. It includes tools for:
- Describing existing rules
- Installing new rules
- Listing all installed rules
- Uninstalling rules

Each tool is implemented as a class that inherits from OpenAIFunction, providing
a standardized interface for GPT to interact with the rule management system.
"""

import json
from typing import override

from pydantic import BaseModel

from gpt.functions import OpenAIFunction
from hubitat.rules.manager import RuleManager
from hubitat.rules.model import ModelAction, Rule


class StringValue(BaseModel):
    """A Pydantic model for a string value"""

    value: str


class Empty(BaseModel):
    """A Pydantic model for an empty value"""


class ActionList(BaseModel):
    """A Pydantic model for a list of actions"""

    actions: list[ModelAction]


class DescribeRuleTool(OpenAIFunction[StringValue]):
    """A GPT function for describing rules"""

    def __init__(self, rule_manager: RuleManager):
        self._rule_manager = rule_manager

    def get_name(self) -> str:
        return 'describe_rule'

    def get_description(self) -> str:
        return 'Use this function to get a detailed description of a rule'

    # pylint: disable=arguments-renamed
    @override
    async def execute(self, rule_name: StringValue) -> str:
        rule = self._rule_manager.get_rule_by_name(rule_name.value)
        if rule is None:
            return f"Rule '{rule_name.value}' not found"
        return rule.model_dump_json()


class ExecuteActionsTool(OpenAIFunction[ActionList]):
    """A GPT function for executing actions"""

    def __init__(self, rule_manager: RuleManager):
        self._rule_manager = rule_manager

    def get_name(self) -> str:
        return 'execute_actions'

    def get_description(self) -> str:
        return 'Use this function to execute a list of actions'

    # pylint: disable=arguments-renamed
    @override
    async def execute(self, actions: ActionList) -> str:
        await self._rule_manager.invoke_actions(actions.actions)
        return 'Actions executed successfully'


class InstallRuleTool(OpenAIFunction[Rule]):
    """A GPT function for installing rules"""

    def __init__(self, rule_manager: RuleManager):
        self._rule_manager = rule_manager

    def get_name(self) -> str:
        return 'install_rule'

    def get_description(self) -> str:
        return 'Use this function to install a rule'

    # pylint: disable=arguments-renamed
    @override
    async def execute(self, rule: Rule) -> str:
        await self._rule_manager.install_rule(rule)
        return 'Rule installed successfully'


class ListAllRulesTool(OpenAIFunction[Empty]):
    """A GPT function for listing all rules"""

    def __init__(self, rule_manager: RuleManager):
        self._rule_manager = rule_manager

    def get_name(self) -> str:
        return 'list_all_rules'

    def get_description(self) -> str:
        return 'Use this function to get a summary of all current rules'

    # pylint: disable=arguments-renamed
    @override
    async def execute(self, _: Empty) -> list[Rule]:
        rules = self._rule_manager.get_installed_rules()
        return json.dumps([{
            'name': rule.name,
            'description': rule.description,
        } for rule in rules])


class UninstallRuleTool(OpenAIFunction[StringValue]):
    """A GPT function for uninstalling rules"""

    def __init__(self, rule_manager: RuleManager):
        self._rule_manager = rule_manager

    def get_name(self) -> str:
        return 'uninstall_rule'

    def get_description(self) -> str:
        return 'Use this function to uninstall a rule'

    # pylint: disable=arguments-renamed
    @override
    async def execute(self, rule_name: StringValue) -> str:
        self._rule_manager.uninstall_rule(rule_name.value)
        return 'Rule uninstalled successfully'
