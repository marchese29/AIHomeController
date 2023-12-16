import asyncio as aio
from pydantic import BaseModel, Field
from threading import Thread
import time
from typing import Callable, Dict

from gpt.client import OpenAISession
from gpt.functions import OpenAIFunction


class TimerRequest(BaseModel):
    name: str = Field(description='The name of the timer, this must be unique among all running timers.')
    seconds: int = Field(description='The number of seconds on the timer', gt=0)


def fire_timer_with_delay(name: str, session: OpenAISession, seconds: int, callback: Callable[[], None]):
    time.sleep(seconds)
    aio.run(session.handle_timer_event(name))
    callback()


class TimerFunction(OpenAIFunction[TimerRequest]):
    """GPT Function for executing a timer."""

    def __init__(self, ai_session: OpenAISession):
        self._ai_session = ai_session
        self._timers: Dict[str, Thread] = {}

    def get_name(self) -> str:
        return 'set_timer'

    def get_description(self) -> str:
        return 'Use this function to initiate a timer which will trigger after a delay'

    async def execute(self, request: TimerRequest) -> str:
        if request.name in self._timers:
            return f'Failed, a timer named "{request.name}" already exists'

        def callback():
            del self._timers[request.name]

        print(f'Scheduling {request.seconds} second "{request.name}" timer')
        self._timers[request.name] = Thread(target=fire_timer_with_delay,
                                            args=(request.name, self._ai_session, request.seconds, callback))
        self._timers[request.name].start()
        return 'Success'
