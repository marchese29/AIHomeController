import asyncio as aio
import json
from pydantic import BaseModel, Field
from typing import List

from .client import HubitatClient, HubitatDevice
from gpt.functions import OpenAIFunction


class DeviceQueryItem(BaseModel):
    device_id: int = Field(description='The ID of the device whose state is being queried')
    attribute: str = Field(description='The name of the device attribute to get the value for')


class DeviceQueryList(BaseModel):
    queries: List[DeviceQueryItem] = Field(description='The list of queries for device state')


class DeviceQueryFunction(OpenAIFunction[DeviceQueryList]):
    """A function for querying device state"""

    def __init__(self, he_client: HubitatClient):
        self._devices = he_client.devices
        self._he_client = he_client

        attr_set = set()
        for device in self._devices:
            attr_set.union(device.attributes)
        self._attributes = [a for a in attr_set]

    def get_name(self) -> str:
        return 'get_device_attribute'

    def get_description(self) -> str:
        return 'Use this function to get the current value of a device attribute'

    async def execute(self, queries: DeviceQueryList) -> str:
        tasks = []
        for query in queries.queries:
            tasks.append(aio.create_task(self._he_client.get_attribute(query.device_id, query.attribute)))
        results = await aio.gather(*tasks)
        return json.dumps(dict(zip([f'{q.device_id}_{q.attribute}' for q in queries.queries], results)))


class LayoutRequest(BaseModel):
    rooms: List[str] = Field(description="The list of rooms to get the device ID's for")


class LayoutFunction(OpenAIFunction[LayoutRequest]):
    """GPT function for reporting the layout of the house."""

    def __init__(self, devices: List[HubitatDevice]):
        self._devices = devices

    def get_name(self) -> str:
        return 'get_devices_for_room'

    def get_description(self) -> str:
        return 'Use this function to get the list of device IDs for any rooms.'

    async def execute(self, request: LayoutRequest) -> str:
        return json.dumps({room: [dev.id for dev in self._devices if dev.room == room] for room in request.rooms})
