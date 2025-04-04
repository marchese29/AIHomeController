"""Timer service for managing asynchronous timers with unique IDs.

This module provides a TimerService class that manages multiple asynchronous timers.
Each timer has a unique ID, duration, and callback function that executes when the timer expires.
The service supports starting, canceling, and resetting timers, with automatic cleanup
of completed timers.
"""

import asyncio as aio
from asyncio import Task
from dataclasses import dataclass
from datetime import timedelta
from typing import Awaitable, Callable


@dataclass
class Timer:
    """Represents a single timer with its properties and state."""

    id: str
    duration: timedelta
    callback: Callable[[str], Awaitable[None]]
    task: Task


class TimerService:
    """Manages multiple timers with unique IDs, durations, and callbacks."""

    def __init__(self):
        self._timers: dict[str, Timer] = {}

    async def start_timer(
        self,
        timer_id: str,
        duration: timedelta,
        callback: Callable[[str], Awaitable[None]],
    ) -> None:
        """Start a new timer with the given ID, duration, and callback.

        Args:
            timer_id: Unique identifier for the timer
            duration: How long to wait before triggering the callback
            callback: Async function to call when the timer expires, taking the timer_id as argument

        Raises:
            ValueError: If a timer with the given ID already exists
        """
        if timer_id in self._timers:
            self.cancel_timer(timer_id)

        async def timer_task():
            try:
                await aio.sleep(duration.total_seconds())
                await callback(timer_id)
            finally:
                if timer_id in self._timers:
                    del self._timers[timer_id]

        timer = Timer(
            id=timer_id,
            duration=duration,
            callback=callback,
            task=aio.create_task(timer_task()),
        )
        self._timers[timer_id] = timer

    def cancel_timer(self, timer_id: str) -> bool:
        """Cancel a timer by its ID.

        Args:
            timer_id: ID of the timer to cancel

        Returns:
            True if the timer was found and cancelled, False otherwise
        """
        if timer_id not in self._timers:
            return False

        timer = self._timers[timer_id]
        if not timer.task.done():
            timer.task.cancel()
        del self._timers[timer_id]
        return True

    async def reset_timer(self, timer_id: str) -> bool:
        """Reset a timer by cancelling it and starting it again with the same duration and callback.

        Args:
            timer_id: ID of the timer to reset

        Returns:
            True if the timer was found and reset, False otherwise
        """
        if timer_id not in self._timers:
            return False

        timer = self._timers[timer_id]
        if not timer.task.done():
            timer.task.cancel()

        # Start a new timer with the same parameters
        await self.start_timer(timer_id, timer.duration, timer.callback)
        return True
