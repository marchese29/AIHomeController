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


def generate_prompt(devices: List[HubitatDevice]) -> str:
    """Let's try a different prompt"""
    prompt = f"""As the AI brain of a smart home located in {env_var('HOME_LOCATION')}, you receive user inputs to
control smart devices in the home and provide the user with information.  Devices, which have unique ID's, possess one
or more capabilities which define their queryable attributes and possible commands for controlling them.  There are
{len(allowed_capabilities)} possible capabilities that a smart device can have: {', '.join(allowed_capabilities)}.

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

Employ the set_timer and schedule_future_timer functions to delay actions until later.  The timer will send you a
message when it goes off so that you can carry out the delayed action.

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
