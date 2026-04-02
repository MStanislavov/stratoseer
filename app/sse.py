from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any, AsyncGenerator


class RunEventManager:
    """Manages per-run SSE event queues with history replay for late subscribers."""

    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue[dict[str, Any] | None]]] = defaultdict(list)
        self._history: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._closed: set[str] = set()

    def subscribe(self, run_id: str) -> asyncio.Queue[dict[str, Any] | None]:
        """Create a queue pre-filled with event history for the given run."""
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        for event in self._history.get(run_id, []):
            queue.put_nowait(event)
        if run_id in self._closed:
            queue.put_nowait(None)
        else:
            self._queues[run_id].append(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue[dict[str, Any] | None]) -> None:
        """Remove a previously registered event queue for the given run."""
        if run_id in self._queues:
            self._queues[run_id] = [q for q in self._queues[run_id] if q is not queue]

    async def publish(self, run_id: str, event: dict[str, Any]) -> None:
        """Broadcast an event to all subscribers and store in history."""
        self._history[run_id].append(event)
        for queue in self._queues.get(run_id, []):
            await queue.put(event)

    async def close(self, run_id: str) -> None:
        """Send a termination sentinel to live subscribers and mark run as closed."""
        self._closed.add(run_id)
        for queue in self._queues.get(run_id, []):
            await queue.put(None)
        self._queues.pop(run_id, None)

    async def event_stream(self, run_id: str) -> AsyncGenerator[dict[str, Any], None]:
        """Yield event dicts until the run completes (sse_starlette handles formatting)."""
        queue = self.subscribe(run_id)
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield {"data": json.dumps(event)}
        finally:
            self.unsubscribe(run_id, queue)


event_manager = RunEventManager()
