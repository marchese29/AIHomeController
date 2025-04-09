"""Module for managing clock-based triggers that fire at specific times of day."""

import asyncio as aio
from asyncio import Queue, Task
from dataclasses import dataclass
from datetime import datetime, time
from typing import Awaitable, Callable, Optional


@dataclass
class ClockRequest:
    """Represents a request to start a clock trigger."""

    id: str
    trigger_time: time
    callback: Callable[[str], Awaitable[None]]


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
        self._queue: Queue[ClockRequest] = Queue()
        self._processor_task: Optional[Task] = None

    def start(self):
        """Start the clock service and its background processor.

        Returns:
            Task: The background task that can be awaited by the server process
        """
        if self._processor_task is None:
            self._processor_task = aio.create_task(self._process_queue())

    async def stop(self) -> None:
        """Stop the clock service and its background processor."""
        if self._processor_task is not None:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except aio.CancelledError:
                pass
            self._processor_task = None

    async def _process_queue(self) -> None:
        """Background task that processes clock requests from the queue."""
        while True:
            try:
                request = await self._queue.get()
                await self._start_clock_internal(request)
            except aio.CancelledError:
                break
            except Exception as e:
                print(f"Error processing clock request: {e}")

    async def _start_clock_internal(self, request: ClockRequest) -> None:
        """Internal method to start a clock trigger with the given request."""
        if request.id in self._clocks:
            self.cancel_clock(request.id)

        async def clock_task():
            while True:
                now = datetime.now()
                next_trigger = datetime.combine(now.date(), request.trigger_time)

                # If the trigger time has already passed today, schedule for tomorrow
                if next_trigger < now:
                    next_trigger = datetime.combine(
                        now.date().replace(day=now.day + 1), request.trigger_time
                    )

                # Calculate seconds until next trigger
                wait_seconds = (next_trigger - now).total_seconds()

                try:
                    await aio.sleep(wait_seconds)
                    await request.callback(request.id)
                except aio.CancelledError:
                    return

        clock = Clock(
            id=request.id,
            trigger_time=request.trigger_time,
            callback=request.callback,
            task=aio.create_task(clock_task()),
        )
        self._clocks[request.id] = clock

    async def start_clock(
        self,
        clock_id: str,
        trigger_time: time,
        callback: Callable[[str], Awaitable[None]],
    ) -> None:
        """Queue a request to start a new clock trigger that will fire at the specified
        time each day.

        Args:
            clock_id: Unique identifier for the clock trigger
            trigger_time: Time of day when the callback should be triggered
            callback: Async function to call when the time is reached, taking the clock_id
                      as argument
        """
        request = ClockRequest(
            id=clock_id, trigger_time=trigger_time, callback=callback
        )
        await self._queue.put(request)

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
        """Reset a clock trigger by cancelling it and starting it again with the same time
        and callback.

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

        # Queue a new clock trigger with the same parameters
        await self.start_clock(clock_id, clock.trigger_time, clock.callback)
        return True
