from typing import Literal, Annotated, Optional

from pydantic import BaseModel, Field


class DeviceCondition(BaseModel):
    kind: Literal['device_condition']
    device_id: int = Field(description='The ID of the device to check the condition for')
    attribute: str = Field(description='The name of the device attribute to check the value for')
    operator: Literal['=', '!=', '<', '<=', '>', '>='] = Field(description='The comparison operator to use')
    value: str | int | float | bool = Field(description='The value to compare the attribute value to')


class BooleanCondition(BaseModel):
    kind: Literal['boolean_condition']
    operator: Literal['and', 'or', 'not']
    conditions: list['StateCondition'] = Field(description='The list of conditions to combine')


StateCondition = Annotated[DeviceCondition | BooleanCondition, Field(discriminator='kind')]


class DeviceControlAction(BaseModel):
    kind: Literal['device_control']
    device_id: int = Field(description='The ID of the device to control')
    command: str = Field(description='The command to send to the device')
    arguments: Optional[list[str | int | float | bool]] = Field(default=None, description='Optional list of arguments to pass with the command')


class IfThenElseAction(BaseModel):
    kind: Literal['if_then_else']
    if_condition: StateCondition = Field(description='The condition to check')
    then_actions: list['Action'] = Field(description='The actions to perform if the condition is true')
    else_actions: Optional[list['Action']] = Field(default=None, description='The actions to perform if the condition is false')


class UntilAction(BaseModel):
    kind: Literal['until']
    condition: StateCondition = Field(description='The condition to wait for')
    timeout: Optional[int] = Field(default=None, description='The maximum number of seconds to wait for the condition to be true')
    until_actions: list['Action'] = Field(description='The actions to perform once the condition has been met')
    timeout_actions: Optional[list['Action']] = Field(default=None, description='The actions to perform if the timeout is reached')


class WaitAction(BaseModel):
    kind: Literal['wait']
    condition: StateCondition = Field(description='The condition to wait for')
    timeout: Optional[int] = Field(default=None, description='The maximum number of seconds to wait for the condition to be true')


Action = Annotated[DeviceControlAction | IfThenElseAction | UntilAction | WaitAction, Field(discriminator='kind')]


class Rule(BaseModel):
    name: str = Field(description='The rule\'s name')
    description: str = Field(description='A brief one sentence description of the rule')
    trigger: StateCondition = Field(description='The condition that triggers the actions')
    actions: list[Action] = Field(description='The actions to perform when the rule is triggered')
