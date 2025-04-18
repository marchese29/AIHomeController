import asyncio as aio
from datetime import datetime
from typing import cast

from hubitat.rules.conditions import AbstractCondition
from hubitat.rules.engine import RuleEngine
from hubitat.rules.parser import AbstractRule, RuleUtilities, TriggerTimeProvider


class RuleHandler:
    """A handler for rules."""

    def __init__(self, rule_engine: RuleEngine):
        self._rule_engine = rule_engine
        self._rules: dict[str, AbstractRule] = {}
        self._rule_tasks: dict[str, aio.Task] = {}

    ####################
    # PUBLIC INTERFACE #
    ####################

    def install_rule(self, rule_code: str):
        """Install a rule from a string of code."""
        rule = self._rule_engine.parse_rule(rule_code)
        self._install_rule(rule)

    async def uninstall_rule(self, rule_name: str):
        """Uninstall a rule."""
        del self._rules[rule_name]
        if rule_name in self._rule_tasks:
            task = self._rule_tasks[rule_name]
            if not task.done():
                task.cancel()
                await task
        del self._rule_tasks[rule_name]

    #############
    # INTERNALS #
    #############

    def _install_rule(self, rule: AbstractRule):
        self._rules[rule.name] = rule

        if isinstance(rule.trigger, TriggerTimeProvider):
            provider = cast(TriggerTimeProvider, rule.trigger)
            self._rule_tasks[rule.name] = aio.create_task(
                self._run_rule_on_timers(rule, provider)
            )

            def _cleanup_rule_task(task: aio.Task):
                del self._rule_tasks[rule.name]

            self._rule_tasks[rule.name].add_done_callback(_cleanup_rule_task)
        elif isinstance(rule.trigger, AbstractCondition):
            self._rule_tasks[rule.name] = aio.create_task(
                self._run_rule_on_condition(rule)
            )

            def _cleanup_rule_task(task: aio.Task):
                del self._rule_tasks[rule.name]

            self._rule_tasks[rule.name].add_done_callback(_cleanup_rule_task)
        else:
            raise ValueError(f"Invalid trigger type: {type(rule.trigger)}")

    async def _run_rule_on_timers(
        self, rule: AbstractRule, provider: TriggerTimeProvider
    ):
        while (next_trigger := provider()) is not None:
            # You get three attempts to give me a trigger in the future before I give up
            if next_trigger <= datetime.now():
                i = 0
                while next_trigger <= datetime.now() and i < 2:
                    i += 1
                    next_trigger = provider()
                if next_trigger <= datetime.now():
                    return

            # Wait until the trigger time then run the rule
            wait = next_trigger - datetime.now()
            await aio.sleep(wait.total_seconds())
            await rule.run(RuleUtilities(self._rule_engine))

    async def _run_rule_on_condition(self, rule: AbstractRule):
        while True:
            # Wait for the condition to be true
            event = aio.Event()
            self._rule_engine.add_condition(rule.trigger, condition_event=event)
            await event.wait()

            # Remove the condition while running the rule
            self._rule_engine.remove_condition(rule.trigger)

            # Run the rule
            await rule.run(RuleUtilities(self._rule_engine))
