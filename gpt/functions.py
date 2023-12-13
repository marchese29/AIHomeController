from abc import ABC, abstractmethod
import json
from pydantic import BaseModel
from typing import Any, Dict, List

from hubitat.client import HubitatClient
from util import JSONObject


class FunctionTool(ABC):
    """Represents a tool callable from OpenAI"""

    @abstractmethod
    def get_name(self) -> str:
        """Returns the name of this tool"""
        pass

    @abstractmethod
    def get_definition(self) -> JSONObject:
        """Returns the tool definition for this function"""
        pass

    @abstractmethod
    async def execute(self, arguments: str) -> str:
        """Executes this tool"""
        pass


class DeviceCommandItem(BaseModel):
    device_id: int
    command: str


class DeviceCommandList(BaseModel):
    commands: List[DeviceCommandItem]


class DeviceCommandTool(FunctionTool):
    """A GPT function tool for commanding devices"""

    def __init__(self, he_client: HubitatClient):
        self._devices = he_client.devices
        self._he_client = he_client

        command_set = set()
        for device in self._devices:
            command_set.union(device.commands)
        self._commands = [c for c in command_set]

    def get_name(self) -> str:
        return 'control_device'

    def get_definition(self) -> JSONObject:
        return {
            'type': 'function',
            'function': {
                'name': self.get_name(),
                'description': 'Use this function to control a device in the smart home by issuing it a command',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'commands': {
                            'type': 'array',
                            'items': {
                                'type': 'object',
                                'properties': {
                                    'device_id': {
                                        'type': 'integer',
                                        'enum': [int(d.id) for d in self._devices],
                                        'description': 'The ID of the device to issue the command to'
                                    },
                                    'command': {
                                        'type': 'string',
                                        'enum': [c.name for c in self._commands],
                                        'description': 'The command to issue to the device'
                                    }
                                },
                                'required': ['device_id', 'capability', 'command']
                            }
                        }
                    }
                }
            }
        }

    async def execute(self, arguments: str) -> str:
        commands = DeviceCommandList.model_validate_json(arguments).commands
        for command in commands:
            await self._he_client.send_command(command.device_id, command.command)

        # TODO: Partial failures?
        return 'Success'


class DeviceQueryItem(BaseModel):
    device_id: int
    attribute: str


class DeviceQueryList(BaseModel):
    queries: List[DeviceQueryItem]


class DeviceQueryTool(FunctionTool):
    """A tool for querying device state"""

    def __init__(self, he_client: HubitatClient):
        self._devices = he_client.devices
        self._he_client = he_client

        attr_set = set()
        for device in self._devices:
            attr_set.union(device.attributes)
        self._attributes = [a for a in attr_set]

    def get_name(self) -> str:
        return 'get_device_attribute'

    def get_definition(self) -> JSONObject:
        return {
            'type': 'function',
            'function': {
                'name': self.get_name(),
                'description': 'Use this function to get the current value of a device attribute',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'queries': {
                            'type': 'array',
                            'items': {
                                'type': 'object',
                                'properties': {
                                    'device_id': {
                                        'type': 'integer',
                                        'enum': [int(d.id) for d in self._devices],
                                        'description': 'The ID of the device whose state is being queried'
                                    },
                                    'attribute': {
                                        'type': 'string',
                                        'enum': [a.name for a in self._attributes],
                                        'description': 'The name of the device attribute to get the value for'
                                    }
                                },
                                'required': ['device_id', 'attribute']
                            }
                        }
                    }
                }
            }
        }

    async def execute(self, arguments: str) -> str:
        queries = DeviceQueryList.model_validate_json(arguments).queries
        values: Dict[int, Any] = {}
        for query in queries:
            result = await self._he_client.get_attribute(query.device_id, query.attribute)
            values[query.device_id] = result
        return json.dumps(values)
