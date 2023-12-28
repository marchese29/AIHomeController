import asyncio as aio
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import pytz
from threading import Thread
import time
from typing import Callable, Dict

from gpt.client import OpenAISession
from gpt.functions import OpenAIFunction


class TimerRequest(BaseModel):
    name: str = Field(description='The name of the timer, this must be unique among all running timers.')
    weeks: int = Field(description='The number of weeks on the timer', ge=0, default=0)
    days: int = Field(description='The number of days on the timer', ge=0, default=0)
    hours: int = Field(description='The number of hours on the timer', ge=0, default=0)
    minutes: int = Field(description='The number of minutes on the timer', ge=0, default=0)
    seconds: int = Field(description='The number of seconds on the timer', ge=0, default=0)


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
        diff_data = request.model_dump()
        name = diff_data.pop('name')
        if name in self._timers:
            return f'Failed, a timer named "{name}" already exists'

        def callback():
            del self._timers[name]

        diff = timedelta(**diff_data)
        self._timers[name] = Thread(target=fire_timer_with_delay,
                                    args=(name, self._ai_session, diff.total_seconds(), callback))
        self._timers[name].start()
        return 'Success'


class ScheduleRequest(BaseModel):
    name: str = Field(description='A name for the request, must be unique')
    time: datetime = Field(description='The time at which to trigger the future action')


class ScheduledTimerFunction(OpenAIFunction[ScheduleRequest]):
    """GPT Function for executing a scheduled timer"""

    def __init__(self, ai_session: OpenAISession):
        self._ai_session = ai_session
        self._timers: Dict[str, Thread] = {}

    def get_name(self) -> str:
        return 'schedule_future_action'

    def get_description(self) -> str:
        return 'Use this function to schedule an action which will trigger at a specific time'

    async def execute(self, request: ScheduleRequest) -> str:
        if request.name in self._timers:
            return f'Failed, a timer named "{request.name}" already exists'
        if request.time < datetime.now(request.time.tzinfo):
            return f'Failed, timers must occur in the future'

        def callback():
            del self._timers[request.name]

        diff = request.time - datetime.now(request.time.tzinfo)
        self._timers[request.name] = Thread(target=fire_timer_with_delay,
                                            args=(request.name, self._ai_session, diff.total_seconds(), callback()))
        self._timers[request.name].start()
        return 'Success'


class TimeDifferenceRequest(BaseModel):
    time: datetime = Field(description='The time to measure the difference from')


class TimeDifferenceFunction(OpenAIFunction[TimeDifferenceRequest]):
    """GPT Function for retrieving the difference in seconds between a time and now"""

    def get_name(self) -> str:
        return 'get_elapsed_time_until'

    def get_description(self) -> str:
        return 'Use this function to get the number of seconds that will elapse between now and a given time'

    async def execute(self, request: TimeDifferenceRequest) -> str:
        now = datetime.now(request.time.tzinfo)
        if now >= request.time:
            return f'Error: {request.time.isoformat()} is in the past'

        return f'{request.time.isoformat()} will be in {request.time - now}'


class CurrentTimeRequest(BaseModel):
    timezone_name: str = Field(description='The IANA name for the timezone that you need the current time in')


class CurrentTimeFunction(OpenAIFunction[CurrentTimeRequest]):
    """GPT Function for retrieving the current time of day."""

    def get_name(self) -> str:
        return 'get_current_time'

    def get_description(self) -> str:
        return "Use this function to get the current time of day in a desired timezone"

    async def execute(self, request: CurrentTimeRequest) -> str:
        tz = pytz.timezone(request.timezone_name)
        dt = datetime.now(tz)
        return dt.isoformat()
