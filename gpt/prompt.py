"""Module for generating prompts for the AI assistant that controls smart home devices.
This module handles loading and processing prompt templates, and formatting them with
device information, capabilities, and examples."""

import json
import random
import os

from hubitat.client import (
    allowed_capabilities,
    capability_attributes,
    capability_commands,
    HubitatDevice,
)
from util import env_var


def summarize_capability(capability: str) -> str:
    """Generate a human-readable summary of a device capability's attributes and commands.

    Args:
        capability: The name of the capability to summarize.

    Returns:
        A formatted string containing the capability's attributes and commands with their
        value types, restrictions, and arguments.
    """
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


def generate_prompt(devices: list[HubitatDevice]) -> str:
    """Generate the prompt by loading and processing the template file"""

    # Prepare all the variables for template substitution
    rooms = list(set(d.room for d in devices))
    devices_list = "\n".join(
        f"- {device.label} (ID: {device.id}) ~ Capabilities: {', '.join(device.capabilities)}"
        for device in devices)
    capabilities_details = "\n".join(f"- {summarize_capability(capability)}"
                                     for capability in allowed_capabilities)

    # Get example device and its details
    command_mapping = {cap: [com.model_dump(exclude_none=True) for com in capability_commands[cap]]
                       for cap in allowed_capabilities if len(capability_commands[cap]) > 0}
    cap_example = random.sample(list(command_mapping.keys()), 1)[0]
    example_device = [d for d in devices if cap_example in d.capabilities][0]

    example_attributes = []
    example_commands = []
    example_device_capabilities = []
    for capability in example_device.capabilities:
        example_attributes.extend(
            [a.name for a in capability_attributes[capability]])
        example_commands.extend(
            [c.name for c in capability_commands[capability]])
        example_device_capabilities.append(summarize_capability(capability))

    # Format the template with all variables
    template_path = os.path.join(
        os.path.dirname(__file__), 'prompt_template.txt')
    with open(template_path, 'r', encoding='utf-8') as f:
        template = f.read()
    return template.format(
        home_location=env_var('HOME_LOCATION'),
        num_capabilities=len(allowed_capabilities),
        capabilities_list=', '.join(allowed_capabilities),
        devices_list=devices_list,
        num_rooms=len(rooms),
        rooms_list=', '.join(rooms),
        capabilities_details=capabilities_details,
        example_device=example_device,
        example_device_capabilities='\n'.join(example_device_capabilities),
        example_attributes=', '.join(example_attributes),
        example_commands=', '.join(example_commands)
    )
