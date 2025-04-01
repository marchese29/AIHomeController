import asyncio as aio
import os
from typing import Optional

from hubitat.client import HubitatClient
from hubitat.rules.condition import Condition, condition_for_model
from hubitat.rules.manager import ConditionManager
from hubitat.rules.model import BooleanCondition, DeviceCondition
from hubitat.rules.process import Action, RuleProcessManager
from hubitat.scenes.model import Scene
from util import env_var, load_models_from_json, save_models_to_json


class _Scene:
    """Represents internally a collection of device states."""

    def __init__(self, model: Scene):
        self._model = model

        setting_conditions: list[BooleanCondition | DeviceCondition] = []
        for setting in model.settings:
            setting_conditions.append(setting.check)
        self._set_trigger = condition_for_model(
            BooleanCondition(operator="and", conditions=setting_conditions)
        )
        self._unset_trigger = condition_for_model(
            BooleanCondition(operator="not", conditions=[self._set_trigger])
        )

    @property
    def model(self) -> Scene:
        """The underlying model for this scene"""
        return self._model

    @property
    def set_trigger(self) -> Condition:
        """The trigger for when the scene is set"""
        return self._set_trigger

    @property
    def unset_trigger(self) -> Condition:
        """The trigger for when the scene is unset"""
        return self._unset_trigger

    @property
    def is_set(self) -> bool:
        """Whether the scene is currently set"""
        return getattr(self, "_is_set", False)

    @is_set.setter
    def is_set(self, value: bool):
        setattr(self, "_is_set", value)


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


class SceneManager:
    """Manager for scenes (multi-device controls)"""

    def __init__(self, he_client: HubitatClient, rule_process: RuleProcessManager):
        self._he_client = he_client
        self._scenes: dict[str, _Scene] = {}
        self._rule_process = rule_process
        self._scene_lock = aio.Lock()
        scenes_file = env_var("SCENES_FILE", allow_null=True)
        if scenes_file is None:
            project_root = _find_project_root(os.path.dirname(__file__))
            scenes_file = os.path.join(project_root, "scenes.json")
        self._scenes_file = scenes_file

    async def _save_scenes(self):
        """Save all scenes to the scenes file."""
        scenes = [scene.model for scene in self._scenes.values()]
        await save_models_to_json(scenes, self._scenes_file)

    async def install_saved_scenes(self):
        """Load and install all scenes from the scenes file."""
        scenes = await load_models_from_json(Scene, self._scenes_file)
        for scene in scenes:
            try:
                await self.create_scene(scene)
            except Exception as e:
                print(f"Error installing scene '{scene.name}': {e}")

    async def create_scene(self, scene: Scene):
        """Create a new scene"""
        if scene.name in self._scenes:
            raise ValueError(f"Scene '{scene.name}' already exists")

        # He's ugly, but I still love him all the same
        internal_scene = _Scene(scene)
        internal_scene.set_trigger.action = SceneManager._on_scene_is_set(
            internal_scene
        )
        internal_scene.unset_trigger.action = SceneManager._on_scene_is_unset(
            internal_scene
        )

        # We need to make sure that if the scene is already set when created, we still
        # trigger the action which switches to the unset waiter
        internal_scene.set_trigger.trigger_always = True

        # Add the scene to tracking under the lock safety
        async with self._scene_lock:
            self._scenes[scene.name] = internal_scene
            await self._save_scenes()

        # Add condition for the set trigger (will switch if the scene is already set)
        await self._rule_process.add_condition(internal_scene.set_trigger)

    async def delete_scene(self, scene_name: str):
        """Delete a scene"""
        if scene_name not in self._scenes:
            raise ValueError(f"Scene '{scene_name}' does not exist")

        async with self._scene_lock:
            internal_scene = self._scenes[scene_name]
            await self._rule_process.remove_condition(internal_scene.set_trigger)
            await self._rule_process.remove_condition(internal_scene.unset_trigger)
            del self._scenes[scene_name]
            await self._save_scenes()

    def get_scene(self, scene_name: str) -> Optional[Scene]:
        """Get a scene"""
        return self._scenes.get(scene_name)

    def get_all_scenes(self) -> list[tuple[Scene, bool]]:
        """Get all scenes"""
        return [(scene.model, scene.is_set) for scene in self._scenes.values()]

    async def set_scene(self, scene_name: str):
        """Sets a scene by sending all the appropriate commands.

        Note: this doesn't actually invoke the _on_scene_is_set methods, they will trigger
        automatically from device events in the rule process."""
        scene = self._scenes[scene_name]
        for setting in scene.settings:
            await self._he_client.send_command(
                setting.device_id, setting.command, setting.arguments
            )

    @staticmethod
    def _on_scene_is_set(scene: _Scene) -> Action:
        async def inner(cm: ConditionManager):
            scene.is_set = True

            # We no longer need to trigger on instantiation
            scene.set_trigger.trigger_always = False

            # Remove the set trigger and add the unset trigger
            await cm.remove_condition(scene.set_trigger)
            await cm.add_condition(scene.unset_trigger)

        return inner

    @staticmethod
    def _on_scene_is_unset(scene: _Scene) -> Action:
        async def inner(cm: ConditionManager):
            scene.is_set = False

            # Remove the unset trigger and add the set trigger
            await cm.remove_condition(scene.unset_trigger)
            await cm.add_condition(scene.set_trigger)

        return inner
