def generate_device_query_tool(devices: list[str]) -> dict[str, any]:
    return {
        'type': 'function',
        'function': {
            'name': 'get_device_state',
            'description': 'Use this function to retrieve the current state of one or more devices in the smart home',
            'parameters': {
                'type': 'object',
                'properties': {
                    'queries': {
                        'type': 'array',
                        'description': 'The list of queries for device state',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'device': {
                                    'type': 'string',
                                    'description': 'The name of the device whose state is to be queried',
                                    'enum': devices
                                },
                                'attribute': {
                                    'type': 'string',
                                    'description': 'The attribute to be retrieved for the device being queried'
                                }
                            },
                            'required': ['device', 'attribute']
                        },
                        'minItems': 1,
                        'uniqueItems': True
                    }
                },
                'required': ['queries']
            }
        }
    }
