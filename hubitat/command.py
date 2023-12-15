import asyncio as aio
from pydantic import BaseModel, Field
from typing import List, Optional

from .client import HubitatClient
from gpt.functions import OpenAIFunction


class DeviceCommandItem(BaseModel):
    device_id: int = Field(description='The ID of the device to issue the command to')
    command: str = Field(description='The command to issue to the device')
    arguments: Optional[List[str | int | float | bool]] = Field(description='The arguments to pass to the command')


class DeviceCommandList(BaseModel):
    commands: List[DeviceCommandItem] = Field(description='The list of commands to issue to devices')


class DeviceCommandFunction(OpenAIFunction[DeviceCommandList]):
    """A GPT function for commanding devices"""

    def __init__(self, he_client: HubitatClient):
        self._devices = he_client.devices
        self._he_client = he_client

        command_set = set()
        for device in self._devices:
            command_set.union(device.commands)
        self._commands = [c for c in command_set]

    def get_name(self) -> str:
        return 'control_device'

    def get_description(self) -> str:
        return 'Use this function to control a device in the smart home by issuing it a command'

    async def execute(self, commands: DeviceCommandList) -> str:
        await aio.gather(
            *[self._he_client.send_command(command.device_id, command.command, arguments=command.arguments) for command
              in commands.commands])

        # TODO: Partial failures?
        return 'Success'
