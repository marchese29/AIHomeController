"""Module for handling device commands in the Hubitat ecosystem.

This module provides functionality to send commands to Hubitat devices through
a structured interface. It defines data models for device commands and implements
a function interface for GPT to interact with devices.
"""

import asyncio as aio
from typing import Optional

from pydantic import BaseModel, Field

from gpt.functions import OpenAIFunction
from hubitat.client import HubitatClient


class DeviceCommandItem(BaseModel):
    """Data model representing a single device command.

    Attributes:
        device_id: The unique identifier of the target device.
        command: The name of the command to execute on the device.
        arguments: Optional list of arguments to pass to the command.
    """
    device_id: int = Field(
        description='The ID of the device to issue the command to')
    command: str = Field(
        description='The name of the command to issue to the device')
    arguments: Optional[list[str | int | float | bool]] = Field(
        description='The arguments to pass to the command')


class DeviceCommandList(BaseModel):
    """Data model representing a list of device commands.

    Attributes:
        commands: List of DeviceCommandItem objects to execute.
    """
    commands: list[DeviceCommandItem] = Field(
        description='The list of commands to issue to devices')


class DeviceCommandFunction(OpenAIFunction[DeviceCommandList]):
    """A GPT function for commanding devices in the Hubitat ecosystem.

    This class implements the OpenAIFunction interface to allow GPT to send
    commands to Hubitat devices. It maintains a list of available devices and
    their supported commands.

    Attributes:
        _devices: List of available Hubitat devices.
        _he_client: HubitatClient instance for communication.
        _commands: Set of all available commands across all devices.
    """

    def __init__(self, he_client: HubitatClient):
        """Initialize the DeviceCommandFunction.

        Args:
            he_client: HubitatClient instance for device communication.
        """
        self._devices = he_client.devices
        self._he_client = he_client

        command_set = set()
        for device in self._devices:
            command_set.union(device.commands)
        self._commands = [c for c in command_set]

    def get_name(self) -> str:
        """Get the name of the function as recognized by GPT.

        Returns:
            str: The function name 'control_device'.
        """
        return 'control_device'

    def get_description(self) -> str:
        """Get the description of the function for GPT.

        Returns:
            str: A description of what the function does.
        """
        return 'Use this function to control a device in the smart home by issuing it a command'

    # pylint: disable=arguments-renamed
    async def execute(self, commands: DeviceCommandList) -> str:
        """Execute a list of device commands asynchronously.

        Args:
            commands: DeviceCommandList containing the commands to execute.

        Returns:
            str: Status message indicating success.

        Note:
            Currently returns 'Success' for all commands. Future implementation
            should handle partial failures and provide more detailed status.
        """
        await aio.gather(
            *[self._he_client.send_command(command.device_id, command.command, arguments=command.arguments) for command
              in commands.commands])

        # TODO: Partial failures?
        return 'Success'
