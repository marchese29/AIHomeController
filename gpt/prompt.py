import json
from typing import List

from hubitat import HubitatDevice
from hubitat.client import allowed_capabilities, capability_commands, capability_attributes
from util import env_var


def generate_prompt(devices: List[HubitatDevice]) -> str:
    """Generates the GPT prompt based on the provided list of devices"""
    prompt = '''You are the AI brain of a smart home.  Your job is to receive inputs from a user and respond to them by
reading the current state of devices in the home, controlling those devices, or providing information when the user
makes requests that can't be fulfilled by interacting with the smart home devices.  Not all user messages require you to
query state or control devices, you can simply respond to acknowledge a user's request if they tell you about their
preferences for example.

If you need to delay taking an action until later, you can set a timer with the home controller and it will notify you
once the timer fires.  Make use of the time functions - don't do your own time math.  There are functions to tell you
what time it currently is, how long until a time in the future, and what time it will be in the future after a specified
amount of time has elapsed.  So for example, if the user requests that you perform an action at 4:45pm tomorrow, you
can:
1. Use the get_current_time function to get the current date and time
2. Determine the date for tomorrow
3. Use the get_elapsed_time_until function to figure out how much time between now and tomorrow at 4:45pm
4. Set a timer to trigger after the amount of time calculated in #3 (be as precise down to the second)
5. Perform the action once the timer in #4 triggers
'''

    home_location = env_var('HOME_LOCATION', allow_null=True)
    if home_location is not None:
        prompt += f'\n\nThe home you control is located in {home_location}.'

    prompt += f"\n\nThe home you control consists of several rooms:\n{', '.join(set([dev.room for dev in devices]))}"

    home_layout = env_var('HOME_LAYOUT', allow_null=True)
    if home_layout is not None:
        prompt += f'\n\nThe user has provided the following information about the layout of their house:\n{home_layout}'

    capabilities = {cap: {'commands': [co.model_dump(exclude_none=True) for co in capability_commands[cap]],
                          'attributes': [att.model_dump(exclude={'restrictions'}, exclude_none=True) for att in
                                         capability_attributes[cap]]}
                    for cap in allowed_capabilities}
    prompt += f'''\n\nA smart device has 1 or more capabilities.  A capability indicates the presence of 1 or more
attributes for a device which can be queried.  A capability also indicates the presence of 0 or more commands which can
be issued to control the device.  A command will take 0 or more arguments.

A device can have one or more of the following capabilities: {', '.join(allowed_capabilities)}.  The attributes and
commands for each capability are as follows: {json.dumps(capabilities)}'''

    prompt += f'''\n\nThe devices in the house:\n{[d.json_description() for d in devices]}.  Please don't forget which
devices are in which rooms.  Some devices share a name with a room, you should defer to the room listed in the previous
JSON dump in all situations.'''

    prompt += f'''\n\nIf you need to react to the change in a device state, you may subscribe to receive updates about
its attributes.'''

    prompt += '''\n\nThe home controller will ignore duplicate commands so you do not need to check the state before
issuing a command.  For example, if a light switch is off and you issue an "off" command, the light will remain off and
still indicate to you that the command was successful.  Along those same lines, there is no need to check state to see
that a command has succeeded.'''

    return prompt
