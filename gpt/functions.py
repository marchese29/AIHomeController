from abc import ABC, abstractmethod
import json
from pydantic import BaseModel, Field
from typing import Any, Dict, Generic, List, Type, TypeVar, get_args, get_origin

from hubitat.client import HubitatClient
from util import JSONObject

M = TypeVar('M', bound=BaseModel)


class OpenAIFunction(Generic[M], ABC):
    """Represents a callable OpenAI function."""

    def _get_model_type(self) -> Type[BaseModel]:
        for base in type(self).__orig_bases__:
            origin = get_origin(base)
            if origin is None or not issubclass(origin, OpenAIFunction):
                continue
            return get_args(base)[0]
        raise Exception("Man, I dunno")

    def get_definition(self) -> JSONObject:
        """Returns the tool definition for this function."""
        return {
            'type': 'function',
            'function': {
                'name': self.get_name(),
                'description': self.get_description(),
                'parameters': self._get_model_type().model_json_schema()
            }
        }

    @abstractmethod
    def get_name(self) -> str:
        """Returns the name of this function."""
        pass

    @abstractmethod
    def get_description(self) -> str:
        """Returns the description of this function."""
        pass

    @abstractmethod
    async def execute(self, arguments: M) -> str:
        """Executes the tool for the given arguments"""
        pass

    async def invoke(self, arguments: str) -> str:
        """Invokes this tool with the provided arguments"""
        return await self.execute(self._get_model_type().model_validate_json(arguments))


class DeviceCommandItem(BaseModel):
    device_id: int = Field(description='The ID of the device to issue the command to')
    command: str = Field(description='The command to issue to the device')


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
        for command in commands.commands:
            await self._he_client.send_command(command.device_id, command.command)

        # TODO: Partial failures?
        return 'Success'


class DeviceQueryItem(BaseModel):
    device_id: int = Field(description='The ID of the device whose state is being queried')
    attribute: str = Field(description='The name of the device attribute to get the value for')


class DeviceQueryList(BaseModel):
    queries: List[DeviceQueryItem] = Field(description='The list of queries for device state')


class DeviceQueryFunction(OpenAIFunction[DeviceQueryList]):
    """A function for querying device state"""

    def __init__(self, he_client: HubitatClient):
        self._devices = he_client.devices
        self._he_client = he_client

        attr_set = set()
        for device in self._devices:
            attr_set.union(device.attributes)
        self._attributes = [a for a in attr_set]

    def get_name(self) -> str:
        return 'get_device_attribute'

    def get_description(self) -> str:
        return 'Use this function to get the current value of a device attribute'

    async def execute(self, queries: DeviceQueryList) -> str:
        values: Dict[int, Any] = {}
        for query in queries.queries:
            result = await self._he_client.get_attribute(query.device_id, query.attribute)
            values[query.device_id] = result
        return json.dumps(values)
