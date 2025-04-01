"""Tools for managing Hubitat scenes through GPT functions.

This module provides a set of GPT function tools that enable interaction with Hubitat
scenes through a natural language interface. It includes tools for:
- Creating new scenes
- Deleting existing scenes
- Listing all installed scenes

Each tool is implemented as a class that inherits from OpenAIFunction, providing
a standardized interface for GPT to interact with the scene management system.
"""

import json
from typing import Literal, override

from pydantic import BaseModel, Field

from gpt.functions import OpenAIFunction
from hubitat.scenes.manager import SceneManager
from hubitat.scenes.model import Scene


class StringValue(BaseModel):
    """A Pydantic model for a string value"""

    value: str


class SceneFilter(BaseModel):
    """A Pydantic model for a scene filter"""

    criteria: Literal["all", "set", "unset"] = Field(
        description="Which scenes to include",
        default="all",
    )


class Empty(BaseModel):
    """A Pydantic model for an empty value"""


class CreateSceneTool(OpenAIFunction[Scene]):
    """A GPT function for creating scenes"""

    def __init__(self, scene_manager: SceneManager):
        self._scene_manager = scene_manager

    def get_name(self) -> str:
        return "create_scene"

    def get_description(self) -> str:
        return "Use this function to create a new scene"

    # pylint: disable=arguments-renamed
    @override
    async def execute(self, scene: Scene) -> str:
        await self._scene_manager.create_scene(scene)
        return f"Scene '{scene.name}' created successfully"


class DeleteSceneTool(OpenAIFunction[StringValue]):
    """A GPT function for deleting scenes"""

    def __init__(self, scene_manager: SceneManager):
        self._scene_manager = scene_manager

    def get_name(self) -> str:
        return "delete_scene"

    def get_description(self) -> str:
        return "Use this function to delete an existing scene"

    # pylint: disable=arguments-renamed
    @override
    async def execute(self, scene_name: StringValue) -> str:
        await self._scene_manager.delete_scene(scene_name.value)
        return f"Scene '{scene_name.value}' deleted successfully"


class ListAllScenesTool(OpenAIFunction[SceneFilter]):
    """A GPT function for listing all scenes"""

    def __init__(self, scene_manager: SceneManager):
        self._scene_manager = scene_manager

    def get_name(self) -> str:
        return "list_all_scenes"

    def get_description(self) -> str:
        return "Use this function to get a summary of all current scenes"

    # pylint: disable=arguments-renamed
    @override
    async def execute(self, scene_filter: SceneFilter) -> str:
        scenes = self._scene_manager.get_all_scenes()
        if scene_filter.criteria != "all":
            scenes = [
                scene
                for scene in scenes
                if (scene.is_set == (scene_filter.criteria == "set"))
            ]
        return json.dumps(
            [
                {
                    **scene.model.model_dump(),
                    "state": "set" if scene.is_set else "unset",
                }
                for scene in scenes
            ]
        )
