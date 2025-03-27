from pydantic import BaseModel
import asyncio as aio
from asyncio import Task
from typing import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, time


@dataclass
class Clock:
    """Represents a single clock trigger with its properties and state."""
    id: str
    trigger_time: time
    callback: Callable[[str], Awaitable[None]]
    task: Task


class ClockService:
    """Manages multiple clock triggers that fire at specific times of day."""

    def __init__(self):
        self._clocks: dict[str, Clock] = {}

    async def start_clock(self, clock_id: str, trigger_time: time, callback: Callable[[str], Awaitable[None]]) -> None:
        """Start a new clock trigger that will fire at the specified time each day.
        
        Args:
            clock_id: Unique identifier for the clock trigger
            trigger_time: Time of day when the callback should be triggered
            callback: Async function to call when the time is reached, taking the clock_id as argument
            
        Raises:
            ValueError: If a clock trigger with the given ID already exists
        """
        if clock_id in self._clocks:
            raise ValueError(f"Clock trigger with ID '{clock_id}' already exists")

        async def clock_task():
            while True:
                now = datetime.now()
                next_trigger = datetime.combine(now.date(), trigger_time)
                
                # If the trigger time has already passed today, schedule for tomorrow
                if next_trigger < now:
                    next_trigger = datetime.combine(now.date().replace(day=now.day + 1), trigger_time)
                
                # Calculate seconds until next trigger
                wait_seconds = (next_trigger - now).total_seconds()
                
                try:
                    await aio.sleep(wait_seconds)
                    await callback(clock_id)
                except aio.CancelledError:
                    return

        clock = Clock(
            id=clock_id,
            trigger_time=trigger_time,
            callback=callback,
            task=aio.create_task(clock_task())
        )
        self._clocks[clock_id] = clock

    def cancel_clock(self, clock_id: str) -> bool:
        """Cancel a clock trigger by its ID.
        
        Args:
            clock_id: ID of the clock trigger to cancel
            
        Returns:
            True if the clock trigger was found and cancelled, False otherwise
        """
        if clock_id not in self._clocks:
            return False

        clock = self._clocks[clock_id]
        if not clock.task.done():
            clock.task.cancel()
        del self._clocks[clock_id]
        return True

    async def reset_clock(self, clock_id: str) -> bool:
        """Reset a clock trigger by cancelling it and starting it again with the same time and callback.
        
        Args:
            clock_id: ID of the clock trigger to reset
            
        Returns:
            True if the clock trigger was found and reset, False otherwise
        """
        if clock_id not in self._clocks:
            return False

        clock = self._clocks[clock_id]
        if not clock.task.done():
            clock.task.cancel()
        
        # Start a new clock trigger with the same parameters
        await self.start_clock(clock_id, clock.trigger_time, clock.callback)
        return True
