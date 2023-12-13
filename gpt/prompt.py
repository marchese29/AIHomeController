import json
from typing import List

from hubitat import HubitatDevice
from util import env_var


def generate_prompt(devices: List[HubitatDevice]) -> str:
    """Generates the GPT prompt based on the provided list of devices"""
    prompt = '''You are the AI brain of a smart home.  Your job is to receive inputs from a user and respond to them by
reading the current state of devices in the home, controlling those devices, or providing information when the user
makes requests that can't be fulfilled by interacting with the smart home devices.'''

    home_location = env_var('HOME_LOCATION', allow_null=True)
    if home_location is not None:
        prompt += f'\n\nThe home you control is located in {home_location}.'

    prompt += f"\n\nThe home you control consists of several rooms:\n{', '.join(set([dev.room for dev in devices]))}"

    home_layout = env_var('HOME_LAYOUT', allow_null=True)
    if home_layout is not None:
        prompt += f'\n\nThe user has provided the following information about the layout of their house:\n{home_layout}'

    prompt += f'''\n\nA smart device contains 0 or more attributes which may be queried for state, and 0 or more
commands which may be issued to the device to control it.  Duplicate commands are ignored by the home controller so, for
example, if you are asked to turn off a switch there is no need to check the switch's state before sending the 'off'
command.

The devices in the house:\n{json.dumps([dev.json_description() for dev in devices])}'''

    return prompt
