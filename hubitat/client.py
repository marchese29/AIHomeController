"""Client module for interacting with Hubitat Elevation hub.

This module provides a Python interface to interact with a Hubitat Elevation hub,
allowing for device control, event subscription, and attribute monitoring.
"""

from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

import httpx
from pydantic import BaseModel, Field

from util import env_var, JSONObject


class DeviceAttribute(BaseModel):
    """Represents a device attribute with its properties and restrictions."""

    name: str
    value_type: str
    restrictions: Optional[Dict[str, Any]] = None
    special_info: Optional[str] = None

    def __hash__(self):
        return hash(self.name)


class CommandArgument(BaseModel):
    """Represents an argument for a device command."""

    name: str
    value_type: str
    restrictions: Dict[str, Any] = {}
    required: bool = False


class DeviceCommand(BaseModel):
    """Represents a command that can be sent to a device."""

    name: str
    arguments: Optional[List[CommandArgument]] = None

    def __hash__(self):
        return hash(self.name)


allowed_capabilities: List[str] = [
    'Switch', 'SwitchLevel', 'MotionSensor', 'ContactSensor',
    'TemperatureMeasurement', 'RelativeHumidityMeasurement', 'GarageDoorControl'
]

capability_attributes: Dict[str, List[DeviceAttribute]] = {
    'Switch': [
        DeviceAttribute(
            name='switch',
            value_type='string',
            restrictions={'enum': ['on', 'off']}
        )
    ],
    'SwitchLevel': [
        DeviceAttribute(
            name='level',
            value_type='integer',
            restrictions={'minimum': 0, 'maximum': 100},
            special_info="A value above 0 indicates that the 'switch' attribute is 'on'"
        )
    ],
    'MotionSensor': [
        DeviceAttribute(
            name='motion',
            value_type='string',
            restrictions={'enum': ['active', 'inactive']},
            special_info="'active' indicates current motion, 'inactive' indicates no motion"
        )
    ],
    'ContactSensor': [
        DeviceAttribute(
            name='contact',
            value_type='string',
            restrictions={'enum': ['closed', 'open']}
        )
    ],
    'TemperatureMeasurement': [
        DeviceAttribute(name='temperature', value_type='number')
    ],
    'RelativeHumidityMeasurement': [
        DeviceAttribute(
            name='humidity',
            value_type='number',
            restrictions={'minimum': 0, 'maximum': 100}
        )
    ],
    'GarageDoorControl': [
        DeviceAttribute(
            name='door',
            value_type='string',
            restrictions={
                'enum': ['unknown', 'closing', 'closed', 'opening', 'open']
            }
        )
    ]
}

capability_commands: Dict[str, List[DeviceCommand]] = {
    'Switch': [DeviceCommand(name=c) for c in ['on', 'off']],
    'SwitchLevel': [
        DeviceCommand(
            name='setLevel',
            arguments=[
                CommandArgument(
                    name='level',
                    value_type='integer',
                    restrictions={'minimum': 0, 'maximum': 100},
                    required=True
                )
            ]
        )
    ],
    'MotionSensor': [],
    'ContactSensor': [],
    'TemperatureMeasurement': [],
    'RelativeHumidityMeasurement': [],
    'GarageDoorControl': [DeviceCommand(name=c) for c in ['open', 'close']]
}


class HubitatDevice(BaseModel):
    """Represents a Hubitat device with its capabilities and attributes."""

    id: str
    label: str
    room: str
    capabilities: List[str]
    attributes: Set[DeviceAttribute]
    commands: Set[DeviceCommand]

    def capabilities_json(self) -> JSONObject:
        """Convert device capabilities to JSON format."""
        return {
            'id': self.id,
            'name': self.label,
            'capabilities': self.capabilities
        }


class DeviceEvent(BaseModel):
    """Represents an event from a Hubitat device."""

    device_id: str = Field(alias='deviceId')
    attribute: str = Field(alias='name')
    value: Optional[Any]


EventCallback = Callable[[DeviceEvent], Awaitable[None]]


class HubitatClient:
    """Wrapper around Hubitat functionalities."""

    def __init__(self):
        """Initialize the Hubitat client with connection details."""
        self._address = f"http://{env_var('HE_ADDRESS')}/apps/api/{env_var('HE_APP_ID')}"
        self._token = env_var('HE_ACCESS_TOKEN')
        self.devices: List[HubitatDevice] = []
        self._subscriptions: Dict[int, Callable[[DeviceEvent], Awaitable[bool]]] = {}

    def load_devices(self):
        """Load all currently-known devices from the Hubitat hub."""
        resp = httpx.get(f"{self._address}/devices/all", params={'access_token': self._token})

        for dev in resp.json():
            caps = [c for c in dev['capabilities'] if isinstance(c, str) and c in allowed_capabilities]
            attributes = set()
            commands = set()
            for capability in caps:
                for attr in capability_attributes[capability]:
                    attributes.add(attr)
                for command in capability_commands[capability]:
                    commands.add(command)
            self.devices.append(
                HubitatDevice(
                    id=dev['id'],
                    label=dev['label'],
                    room=dev['room'],
                    capabilities=caps,
                    attributes=attributes,
                    commands=commands
                )
            )

    async def send_command(
        self, device_id: int, command: str, arguments: Optional[List[Any]] = None
    ):
        """Send a command with optional arguments to a device.

        Args:
            device_id: The ID of the device to send the command to
            command: The command to send
            arguments: Optional list of arguments for the command
        """
        url = f"{self._address}/devices/{device_id}/{command}"
        if arguments:
            url += f"/{','.join(str(arg) for arg in arguments)}"

        with httpx.Client() as client:
            try:
                resp = client.get(
                    url, params={'access_token': self._token}
                )
            except httpx.HTTPStatusError as error:
                raise Exception(
                    f"HE Client returned '{error.response.status_code}' "
                    f"status: {error.response.text}"
                ) from error
            except Exception as error:
                print(f"HE Client returned error: {error}")
                raise

        if resp.status_code != 200:
            raise Exception(
                f"HE Client returned '{resp.status_code}' status: {resp.text}"
            )

    async def get_attribute(self, device_id: int, attribute: str) -> Any:
        """Get the current value of a device attribute.

        Args:
            device_id: The ID of the device to get the attribute from
            attribute: The name of the attribute to get

        Returns:
            The current value of the attribute, or None if not found
        """
        url = f"{self._address}/devices/{device_id}"

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url, params={'access_token': self._token}
            )
        if resp.status_code != 200:
            raise Exception(
                f"HE Client returned '{resp.status_code}' status: {resp.text}"
            )

        attributes: List[Dict[str, Any]] = resp.json()['attributes']
        for attr in attributes:
            if attr['name'] == attribute:
                return attr['currentValue']

        return None

    async def handle_device_event(self, event: Dict[str, Any]) -> bool:
        """Handle a device event by triggering registered callbacks.

        Args:
            event: The event data from the Hubitat hub

        Returns:
            True if a callback was triggered, False otherwise
        """
        device_event = DeviceEvent.model_validate(event)
        print(
            f'Device Event: {device_event.model_dump_json()}'
        )

        device_id = int(device_event.device_id)
        if device_id in self._subscriptions:
            callback = self._subscriptions[device_id]
            return await callback(device_event)
        return False

    def subscribe(self, device_id: int, attributes: List[str], callback: EventCallback):
        """Register a callback for device events.

        Args:
            device_id: The ID of the device to subscribe to
            attributes: List of attribute names to subscribe to
            callback: The callback function to invoke on events
        """
        async def subscription(event: DeviceEvent) -> bool:
            if event.attribute in attributes:
                await callback(event)
                return True
            return False

        self._subscriptions[device_id] = subscription

    def unsubscribe(self, device_id: int):
        """Unregister callbacks for a device.

        Args:
            device_id: The ID of the device to unsubscribe from
        """
        del self._subscriptions[device_id]
