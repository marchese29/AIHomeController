"""Data models for defining automation rules in the Hubitat system.

This module provides Pydantic models for defining automation rules that can be executed
by the Hubitat system. The models support various types of conditions (device states,
boolean logic, time of day) and actions (device control, conditional execution,
waiting, and repeating actions).

The main components are:
- Conditions: DeviceCondition, BooleanCondition, TimeOfDayCondition
- Actions: DeviceControlAction, IfThenElseAction, UntilAction, WaitAction
- Rule: The top-level model that combines a trigger condition with a list of actions
"""

from typing import Literal, Annotated, Optional

from pydantic import BaseModel, Field


class DeviceCondition(BaseModel):
    """A condition that checks a specific device's attribute value.

    This condition evaluates whether a device's attribute matches a specified value using
    a comparison operator. Optionally, it can require the condition to remain true for a
    specified duration before triggering.
    """

    kind: Literal["device"] = Field(default="device")
    device_id: int = Field(
        description="The ID of the device to check the condition for"
    )
    attribute: str = Field(
        description="The name of the device attribute to check the value for"
    )
    operator: Literal["=", "!=", "<", "<=", ">", ">="] = Field(
        description="The comparison operator to use"
    )
    value: str | int | float | bool = Field(
        description="The value to compare the attribute value to"
    )
    duration: Optional[int] = Field(
        default=None,
        description="How long (in seconds) the condition must remain true before triggering actions",
    )


class BooleanCondition(BaseModel):
    """A condition that combines multiple conditions using boolean operators.

    This condition allows for complex logic by combining multiple conditions using AND,
    OR, or NOT operators. It can also require the combined condition to remain true for
    a specified duration.
    """

    kind: Literal["boolean"] = Field(default="boolean")
    operator: Literal["and", "or", "not"] = Field(
        description="The boolean operator to combine conditions"
    )
    conditions: list["StateCondition"] = Field(
        description="The list of conditions to combine"
    )
    duration: Optional[int] = Field(
        default=None,
        description="How long (in seconds) the condition must remain true before triggering actions",
    )


class TimeOfDayCondition(BaseModel):
    """A condition that evaluates based on the current time of day.

    This condition checks if the current time matches specific criteria, such as being
    at, before, or after a specified hour and minute.
    """

    kind: Literal["time_of_day"] = Field(default="time_of_day")
    operator: Literal["is", "after", "before"] = Field(
        description="How to compare the current time"
    )
    hour: int = Field(description="The hour of the day to compare the current time to")
    minute: int = Field(
        description="The minute of the hour to compare the current time to"
    )


StateCondition = Annotated[
    DeviceCondition | BooleanCondition | TimeOfDayCondition, Field(discriminator="kind")
]


class DeviceControlAction(BaseModel):
    """An action that sends a command to a specific device.

    This action allows controlling a device by sending a command with optional arguments.
    The command and arguments are sent to the specified device by its ID.
    """

    kind: Literal["device"] = Field(default="device")
    device_id: int = Field(description="The ID of the device to control")
    command: str = Field(description="The command to send to the device")
    arguments: Optional[list[str | int | float | bool]] = Field(
        default=None, description="Optional list of arguments to pass with the command"
    )


class IfThenElseAction(BaseModel):
    """An action that conditionally executes different sets of actions.

    This action evaluates a condition and executes one set of actions if the condition
    is true, and optionally executes a different set if the condition is false.
    """

    kind: Literal["if_then_else"] = Field(default="if_then_else")
    if_condition: StateCondition = Field(description="The condition to check")
    then_actions: list["ModelAction"] = Field(
        description="The actions to perform if the condition is true"
    )
    else_actions: Optional[list["ModelAction"]] = Field(
        default=None, description="The actions to perform if the condition is false"
    )


class SceneAction(BaseModel):
    """An action that sets a scene.

    This action sets a scene by sending a command to the specified device by its ID.
    """

    kind: Literal["scene"] = Field(default="scene")
    scene_name: str = Field(description="The name of the scene to set")


class UntilAction(BaseModel):
    """An action that repeatedly executes actions until a condition is met.

    This action continuously executes a set of actions until a specified condition
    becomes true. It can optionally timeout after a specified duration and execute
    different actions if the timeout is reached.
    """

    kind: Literal["until"] = Field(default="until")
    condition: StateCondition = Field(description="The condition to wait for")
    timeout: Optional[int] = Field(
        default=None,
        description="The maximum number of seconds to wait for the condition to be true",
    )
    until_actions: list["ModelAction"] = Field(
        description="The actions to perform once the condition has been met"
    )
    timeout_actions: Optional[list["ModelAction"]] = Field(
        default=None, description="The actions to perform if the timeout is reached"
    )


class WaitAction(BaseModel):
    """An action that pauses execution until a condition is met or timeout occurs.

    This action pauses the execution of subsequent actions until either a specified
    condition becomes true or a timeout is reached. It can optionally end the rule
    execution if the timeout is reached.
    """

    kind: Literal["wait"] = Field(default="wait")
    condition: Optional[StateCondition] = Field(
        default=None, description="The condition to wait for"
    )
    timeout: Optional[int] = Field(
        default=None,
        description="The maximum number of seconds to wait for the condition to be true",
    )
    end_on_timeout: bool = Field(
        default=False,
        description="Whether to end the rule execution if the timeout is reached",
    )


ModelAction = Annotated[
    DeviceControlAction | IfThenElseAction | SceneAction | UntilAction | WaitAction,
    Field(discriminator="kind"),
]


class Rule(BaseModel):
    """A rule that defines a set of actions to execute when triggered by a condition.

    A rule consists of a name, description, trigger condition, and a list of actions
    to execute when the trigger condition is met. The trigger condition can be any
    valid state condition, and the actions can include device controls, conditional
    logic, waiting, or repeating actions.
    """

    name: str = Field(description="The rule's name")
    description: str = Field(description="A brief one sentence description of the rule")
    trigger: StateCondition = Field(
        description="The condition that triggers the actions"
    )
    actions: list[ModelAction] = Field(
        description="The actions to perform when the rule is triggered"
    )
