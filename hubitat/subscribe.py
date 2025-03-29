from pydantic import BaseModel, Field
from typing import List

from .client import HubitatClient
from gpt.client import OpenAISession
from gpt.functions import OpenAIFunction


class AttributeSubscription(BaseModel):
    device_id: int = Field(
        description='The ID of the device to be notified of events for')
    attributes: List[str] = Field(
        description='The attributes to receive notifications for', min_length=1)


class SubscriptionList(BaseModel):
    subscriptions: List[AttributeSubscription] = Field(
        description='The list of subscriptions', min_length=1)


class SubscribeFunction(OpenAIFunction[SubscriptionList]):
    """GPT Function for subscribing to device events."""

    def __init__(self, he_client: HubitatClient, ai_session: OpenAISession):
        self._he_client = he_client
        self._ai_session = ai_session

    def get_name(self) -> str:
        return 'subscribe_to_device_events'

    def get_description(self) -> str:
        return 'Use this function to start receiving notifications when device events occur'

    async def execute(self, subscription_list: SubscriptionList) -> str:
        for subscription in subscription_list.subscriptions:
            print(f'ChatGPT has subscribed to changes of "{','.join(subscription.attributes)}" on '
                  f'"{subscription.device_id}"')
            self._he_client.subscribe(subscription.device_id, subscription.attributes,
                                      self._ai_session.handle_device_event)
        return 'Success'


class Unsubscription(BaseModel):
    device_ids: List[int] = Field(
        description='The ID of the devices to unsubscribe from events for', min_length=1)


class UnsubscribeFunction(OpenAIFunction[Unsubscription]):
    """GPT Function for unsubscribing from device events."""

    def __init__(self, he_client: HubitatClient):
        self._he_client = he_client

    def get_name(self) -> str:
        return 'unsubscribe_from_device_events'

    def get_description(self) -> str:
        return 'Use this function to stop receiving device event notifications'

    async def execute(self, unsubscription: Unsubscription) -> str:
        for device_id in unsubscription.device_ids:
            print(f'ChatGPT has unsubscribed from "{device_id}"')
            self._he_client.unsubscribe(device_id)
        return 'Success'
