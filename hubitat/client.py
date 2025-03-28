import httpx
from pydantic import BaseModel, Field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from util import env_var, JSONObject


class DeviceAttribute(BaseModel):
    name: str
    value_type: str
    restrictions: Optional[Dict[str, Any]] = None
    special_info: Optional[str] = None

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
    'SwitchLevel': [DeviceAttribute(name='level', value_type='integer', restrictions={'minimum': 0, 'maximum': 100},
                                    special_info="A value above 0 indicates that the 'switch' attribute is 'on'")],
    'MotionSensor': [
        DeviceAttribute(name='motion', value_type='string', restrictions={'enum': ['active', 'inactive']},
                        special_info="'active' indicates current motion, 'inactive' indicates no motion")],
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

    def capabilities_json(self) -> JSONObject:
        return {
            'id': self.id,
            'name': self.label,
            'capabilities': self.capabilities
        }


class DeviceEvent(BaseModel):
    device_id: str = Field(alias='deviceId')
    attribute: str = Field(alias='name')
    value: Optional[int | str | float | bool]


EventCallback = Callable[[DeviceEvent], Awaitable[None]]


class HubitatClient:
    """Wrapper around Hubitat functionalities"""

    def __init__(self):
        self._address = f"http://{env_var('HE_ADDRESS')}/apps/api/{env_var('HE_APP_ID')}"
        self._token = env_var('HE_ACCESS_TOKEN')
        self.devices: List[HubitatDevice] = []

        self._subscriptions: Dict[int, Callable[[DeviceEvent], Awaitable[bool]]] = {}

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

    async def send_command(self, device_id: int, command: str, arguments: Optional[List[Any]] = None):
        """Sends the provided command with any arguments to the device with the specified device id."""
        url = f"{self._address}/devices/{device_id}/{command}"
        if arguments is not None and len(arguments) > 0:
            url += f"/{','.join([str(a) for a in arguments])}"

        with httpx.Client() as client:
            try:
                resp = client.get(url, params={'access_token': self._token})
            except httpx.HTTPStatusError as e:
                raise Exception(f"HE Client returned '{e.response.status_code}' status: {e.response.text}")
            except BaseException as e:
                print(f"HE Client returned error: {e}")
                raise e
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

    async def handle_device_event(self, event: Dict[str, Any]) -> bool:
        """Triggers any callbacks for subscribers registered on this event"""
        device_event = DeviceEvent.model_validate(event)
        print(f'Device Event: {device_event.model_dump_json()}')

        device_id = int(device_event.device_id)
        if device_id in self._subscriptions:
            callback = self._subscriptions[device_id]
            return await callback(device_event)
        return False

    def subscribe(self, device_id: int, attributes: List[str], callback: EventCallback):
        """Registers the provided callback to be invoked for events on the given device attributes"""

        async def subscription(event: DeviceEvent) -> bool:
            if event.attribute in attributes:
                await callback(event)
                return True
            return False

        self._subscriptions[device_id] = subscription

    def unsubscribe(self, device_id: int):
        """Un-registers any callbacks for the given device"""
        del self._subscriptions[device_id]
