from typing import Dict, List

from hubitat import DeviceCommand, HubitatDevice
from util import JSONObject


def generate_command_tool(command_map: Dict[str, List[DeviceCommand]]) -> JSONObject:
    commands = set()
    for comms in command_map.values():
        for com in comms:
            commands.add(com.name)
    command_item = {
        'type': 'object',
        'properties': {
            'device_id': {
                'type': 'integer',
                'description': 'The ID of the device to issue the command to'
            },
            'command': {
                'type': 'string',
                'enum': [c for c in commands],
                'description': 'The command to issue to the device'
            }
        },
        'required': ['device_id', 'capability', 'command']
    }

    return {
        'type': 'function',
        'function': {
            'name': 'control_device',
            'description': 'Use this function to control a device in the smart home by issuing it a command',
            'parameters': {
                'type': 'object',
                'properties': {
                    'commands': {
                        'type': 'array',
                        'items': command_item
                    }
                }
            }
        }
    }


def generate_device_query_tool(devices: List[HubitatDevice]) -> dict[str, any]:
    attributes = set()
    for device in devices:
        for attribute in device.attributes:
            attributes.add(attribute.name)
    return {
        'type': 'function',
        'function': {
            'name': 'get_device_attribute',
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
                                    'enum': [int(d.id) for d in devices],
                                    'description': 'The ID of the device whose state is being queried'
                                },
                                'attribute': {
                                    'type': 'string',
                                    'enum': [a for a in attributes],
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
