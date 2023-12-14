import httpx
from pydantic import BaseModel
from typing import Any, Dict, List, Optional, Set

from util import env_var, JSONObject


class DeviceAttribute(BaseModel):
    name: str
    value_type: str
    restrictions: Dict[str, Any] = {}

    def __hash__(self):
        return hash(self.name)


class CommandArgument(BaseModel):
    name: str
    value_type: str
    restrictions: Dict[str, Any] = {}
    required: bool = False


class DeviceCommand(BaseModel):
    name: str
    arguments: Optional[List[CommandArgument]] = None

    def __hash__(self):
        return hash(self.name)


allowed_capabilities: List[str] = ['Switch', 'SwitchLevel', 'MotionSensor', 'ContactSensor', 'TemperatureMeasurement',
                                   'RelativeHumidityMeasurement', 'GarageDoorControl']
capability_attributes: Dict[str, List[DeviceAttribute]] = {
    'Switch': [DeviceAttribute(name='switch', value_type='string', restrictions={'enum': ['on', 'off']})],
    'SwitchLevel': [DeviceAttribute(name='level', value_type='integer', restrictions={'minimum': 0, 'maximum': 100})],
    'MotionSensor': [
        DeviceAttribute(name='motion', value_type='string', restrictions={'enum': ['active', 'inactive']})],
    'ContactSensor': [DeviceAttribute(name='contact', value_type='string', restrictions={'enum': ['closed', 'open']})],
    'TemperatureMeasurement': [DeviceAttribute(name='temperature', value_type='number')],
    'RelativeHumidityMeasurement': [
        DeviceAttribute(name='humidity', value_type='number', restrictions={'minimum': 0, 'maximum': 100})],
    'GarageDoorControl': [DeviceAttribute(name='door', value_type='string',
                                          restrictions={'enum': ['unknown', 'closing', 'closed', 'opening', 'open']})]
}
capability_commands: Dict[str, List[DeviceCommand]] = {
    'Switch': [DeviceCommand(name=c) for c in ['on', 'off']],
    'SwitchLevel': [DeviceCommand(name='setLevel', arguments=[
        CommandArgument(name='level', value_type='integer', restrictions={'minimum': 0, 'maximum': 100},
                        required=True)])],
    'MotionSensor': [],
    'ContactSensor': [],
    'TemperatureMeasurement': [],
    'RelativeHumidityMeasurement': [],
    'GarageDoorControl': [DeviceCommand(name=c) for c in ['open', 'close']]
}


class HubitatDevice(BaseModel):
    id: str
    label: str
    room: str
    capabilities: List[str]
    attributes: Set[DeviceAttribute]
    commands: Set[DeviceCommand]

    def json_description(self) -> JSONObject:
        return {
            'id': int(self.id),
            'name': self.label,
            'room': self.room,
            'attributes': [a.name for a in self.attributes],
            'commands': [c.name for c in self.commands]
        }


class HubitatClient:
    """Wrapper around Hubitat functionalities"""

    def __init__(self):
        self._address = f"http://{env_var('HE_ADDRESS')}/apps/api/{env_var('HE_APP_ID')}"
        self._token = env_var('HE_ACCESS_TOKEN')
        self.devices: List[HubitatDevice] = []

    def load_devices(self):
        """Synchronous function which loads all the currently-known devices"""
        resp = httpx.get(f"{self._address}/devices/all", params={'access_token': self._token})

        for dev in resp.json():
            caps = [c for c in dev['capabilities'] if type(c) is str and c in allowed_capabilities]
            attributes = set()
            commands = set()
            for capability in caps:
                for attr in capability_attributes[capability]:
                    attributes.add(attr)
                for command in capability_commands[capability]:
                    commands.add(command)
            self.devices.append(HubitatDevice(id=dev['id'], label=dev['label'], room=dev['room'], capabilities=caps,
                                              attributes=attributes, commands=commands))

    async def send_command(self, device_id: int, command: str, *args: Any):
        """Sends the provided command with any arguments to the device with the specified device id."""
        url = f"{self._address}/devices/{device_id}/{command}"
        if len(args) > 0:
            url += f"/{','.join([str(a) for a in args])}"

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params={'access_token': self._token})
        if resp.status_code != 200:
            raise Exception(f"HE Client returned '{resp.status_code}' status: {resp.text}")

    async def get_attribute(self, device_id: int, attribute: str) -> Any:
        """Gets the current value of the given attribute for the device with the specified device id."""
        url = f"{self._address}/devices/{device_id}"

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params={'access_token': self._token})
        if resp.status_code != 200:
            raise Exception(f"HE Client returned '{resp.status_code}' status: {resp.text}")

        attributes: List[Dict[str, Any]] = resp.json()['attributes']
        for attr in attributes:
            if attr['name'] == attribute:
                return attr['currentValue']

        return None
