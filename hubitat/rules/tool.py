from typing import override

from gpt.functions import OpenAIFunction
from hubitat.rules.manager import RuleManager
from hubitat.rules.model import Rule


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
