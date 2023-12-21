import json
import random
from typing import List

from hubitat.client import allowed_capabilities, capability_attributes, capability_commands, HubitatDevice
from util import env_var


def summarize_capability(capability: str) -> str:
    attributes = capability_attributes[capability]
    result = f"{capability}: Attributes -"
    for attribute in attributes:
        result += f" {attribute.name} (value_type: {attribute.value_type}"
        if attribute.restrictions is not None:
            result += f", value_restrictions: {json.dumps(attribute.restrictions)}"
        result += ")"

    commands = capability_commands[capability]
    if len(commands) == 0:
        return result

    result += ", Commands -"
    for command in commands:
        result += f" {command.name}"
        if command.arguments is not None and len(command.arguments) > 0:
            result += f" (arguments: {json.dumps([a.model_dump() for a in command.arguments])})"

    return result


def generate_alternative_prompt(devices: List[HubitatDevice]) -> str:
    """Let's try a different prompt"""
    prompt = f"""As the AI brain of a smart home, you receive user inputs to control smart devices in the home and
provide the user with information.  Devices, which have unique ID's, possess one or more capabilities which define their
queryable attributes and possible commands for controlling them.  There are {len(allowed_capabilities)} possible
capabilities that a smart device can have: {', '.join(allowed_capabilities)}.

Smart devices are named by the user, you may be able to tell what a device is based on its name but be advised that the
names can be misleading. Smart Devices in the house you control:"""

    for device in devices:
        prompt += f"\n- {device.label} (ID: {device.id}) ~ Capabilities: {', '.join(device.capabilities)}"

    rooms = [r for r in set([d.room for d in devices])]
    prompt += f"""\n\nThe house consists of {len(rooms)} rooms: {', '.join(rooms)}.  To determine a device's room, use the
get_devices_for_room function (do not assume a device's room based solely on its name); devices don't move between
rooms.

You can receive messages for device state changes by subscribing to them with the subscribe_to_device_events function.
You should unsubscribe if you don't need to know about a device's state changes anymore.

Employ the set_timer function to delay actions until later.  The timer will send you a message when it goes off so that
you can carry out the delayed action.

Device capability attributes and commands:"""

    for capability in allowed_capabilities:
        prompt += f"\n- {summarize_capability(capability)}"

    command_mapping = {cap: [com.model_dump(exclude_none=True) for com in capability_commands[cap]] for cap in
                       allowed_capabilities if len(capability_commands[cap]) > 0}

    cap_example = random.sample([c for c in command_mapping.keys()], 1)[0]
    dev_example = [d for d in devices if cap_example in d.capabilities][0]
    attr_examples = []
    comm_examples = []
    for capability in dev_example.capabilities:
        attr_examples.extend([a.name for a in capability_attributes[capability]])
        comm_examples.extend([c.name for c in capability_commands[capability]])
    prompt += f"""\n\nSimple Example:
Suppose you want to determine the attributes and commands for the '{dev_example.label}' (ID: {dev_example.id}).  Refer
to its capabilities:"""

    for capability in dev_example.capabilities:
        prompt += f"\n- {summarize_capability(capability)}"

    prompt += f"""\n\nNow you know you can query the ({', '.join(attr_examples)}) attribute(s) and control the device using the ({', '.join(comm_examples)}) command(s)"""

    prompt += f"""\n\nComplex Example:
Suppose the user requests: 'Whenever motion is detected in the foyer turn on the light in the bedroom closet to 100%
brightness if it is not already on, then turn off the light after 2 minutes.'  You would subscribe to events for the
motion sensor in the foyer, and whenever you receive a message that motion is active you would:
1. Query the current state of the bedroom closet light, if it is already on then there is nothing for you to do.  If the light is off:
2. Command the bedroom closet light to turn on to 100%
3. Set a 2-minute timer and wait for it to fire.  When the timer fires:
4. Turn off the bedroom closet light
5. Repeat the process for any further motion events in the foyer

Especially for more complex requests, there's no need to tell the user everything you are doing behind the scenes."""

    return prompt


def generate_prompt(devices: List[HubitatDevice]) -> str:
    """Generates the GPT prompt based on the provided list of devices"""
    attribute_mapping = {c: [a.model_dump(exclude_none=True) for a in capability_attributes[c]] for c in
                         allowed_capabilities}
    command_mapping = {cap: [com.model_dump(exclude_none=True) for com in capability_commands[cap]] for cap in
                       allowed_capabilities if len(capability_commands[cap]) > 0}

    cap_example = random.sample([c for c in command_mapping.keys()], 1)[0]

    prompt = f'''You are the AI brain of a smart home.  Your job is to receive inputs from a user and respond to them by
reading the current state of smart devices in the home, controlling those smart devices, or providing information when
the user makes requests that can't be fulfilled by interacting with the smart home devices.  Not all user messages
require you to query state or control smart devices, you can simply respond to acknowledge a user's request if they tell
you about their preferences for example.  All of your responses will be read aloud to the resident.

A smart device has one or more queryable attributes which describe its state.  A smart device may also have commands
which allow you to control it, these commands will take zero or more arguments as input.  The attributes and commands
for a given device are defined by its "capabilities" - a device has one or more of the following capabilities:
{', '.join(allowed_capabilities)}.  Here are there available attributes for a device with a given capability:
{json.dumps(attribute_mapping)}.  Here are the available commands for a device with a given capability:
{json.dumps(command_mapping)}.  If a capability does not appear in the previous mapping, then there are no commands. As
an example, if a device has the "{cap_example}" capability, the the attribute mapping indicates that it has
{len(attribute_mapping[cap_example])} attribute(s): {', '.join([a['name'] for a in attribute_mapping[cap_example]])} and
the command mapping indicates that the device has {len(command_mapping[cap_example])} command(s):
{', '.join([c['name'] for c in command_mapping[cap_example]])}.

All smart devices have a unique ID which can be used to send commands and query attributes of the device.  In the house
you control, these are the devices and their capabilities: {json.dumps([dev.capabilities_json() for dev in devices])}

A smart device is in one of the rooms in the house: {', '.join(set([dev.room for dev in devices]))}.  Do not guess what
room a device is in based on the device's name; use the get_devices_for_room function to determine what room a device is
in.  A device will never move between rooms - it will stay in the same place forever.

You may subscribe to receive messages about changes in a smart device's state - these messages can be useful if you need
to performa actions whenever a device changes (for example, a motion sensor detects motion).  You can also unsubscribe
from device state change messages if you no longer need them.

If you need to perform an action at a later time, you can use the set_timer function; this function will send a message
to you when the timer fires.  Make use of the time functions - don't do your own time math.  There are functions to tell
you what time it currently is, how long until a time in the future, and what time it will be in the future after a
specified amount of time has elapsed.  So for example, if the user requests that you perform an action at 4:45pm
tomorrow, you can:
1. Use the get_current_time function to get the current date and time
2. Determine the date for tomorrow
3. Use the get_elapsed_time_until function to figure out how much time between now and tomorrow at 4:45pm
4. Set a timer to trigger after the amount of time calculated in #3 (be precise down to the second)
5. Perform the action once the timer in #4 triggers

The home controller will ignore duplicate commands so you do not need to check the state before
issuing a command.  For example, if a light switch is off and you issue an "off" command, the light will remain off and
still indicate to you that the command was successful.  Along those same lines, there is no need to check state to see
that a command has succeeded.'''

    home_location = env_var('HOME_LOCATION', allow_null=True)
    if home_location is not None:
        prompt += f'\n\nThe home you control is located in {home_location}.'

    home_layout = env_var('HOME_LAYOUT', allow_null=True)
    if home_layout is not None:
        prompt += f'\n\nThe user has provided the following information about the layout of their house:\n{home_layout}'

    return prompt
