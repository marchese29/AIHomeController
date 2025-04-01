from typing import Optional

from pydantic import BaseModel, Field

from hubitat.rules.model import BooleanCondition, DeviceCondition


class SceneSetting(BaseModel):
    """A setting for a scene"""

    device_id: str = Field(description="The ID of the device to set the attribute for")
    command: str = Field(description="The command to send to the device")
    arguments: Optional[list[str | int | float]] = Field(
        default=None, description="The arguments to send to the device"
    )

    check: BooleanCondition | DeviceCondition = Field(
        description="Condition which, if true, indicates the setting is active"
    )


class Scene(BaseModel):
    """A scene is a collection of devices and the state they should be in"""

    name: str
    description: Optional[str] = Field(
        default=None, description="A description of the scene"
    )
    settings: list[SceneSetting] = Field(description="The settings for the scene")


class SceneList(BaseModel):
    """A list of scenes"""

    scenes: list[Scene] = Field(default_factory=list, description="The list of scenes")
