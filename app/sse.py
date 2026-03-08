from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any, AsyncGenerator


class RunEventManager:
    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue[dict[str, Any] | None]]] = defaultdict(list)

    def subscribe(self, run_id: str) -> asyncio.Queue[dict[str, Any] | None]:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._queues[run_id].append(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue[dict[str, Any] | None]) -> None:
        if run_id in self._queues:
            self._queues[run_id] = [q for q in self._queues[run_id] if q is not queue]

    async def publish(self, run_id: str, event: dict[str, Any]) -> None:
        for queue in self._queues.get(run_id, []):
            await queue.put(event)

    async def close(self, run_id: str) -> None:
        for queue in self._queues.get(run_id, []):
            await queue.put(None)
        self._queues.pop(run_id, None)

    async def event_stream(self, run_id: str) -> AsyncGenerator[str, None]:
        queue = self.subscribe(run_id)
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            self.unsubscribe(run_id, queue)


event_manager = RunEventManager()


class LangGraphCallbackHandler:
    """Bridges LangGraph node execution events to SSE."""

    def __init__(self, run_id: str, event_manager: RunEventManager) -> None:
        self.run_id = run_id
        self.event_manager = event_manager

    async def on_node_start(self, node_name: str) -> None:
        from datetime import datetime, timezone

        await self.event_manager.publish(
            self.run_id,
            {
                "type": "agent_started",
                "agent": node_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def on_node_end(self, node_name: str, output: dict[str, Any] | None = None) -> None:
        from datetime import datetime, timezone

        await self.event_manager.publish(
            self.run_id,
            {
                "type": "agent_completed",
                "agent": node_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def on_run_end(self) -> None:
        from datetime import datetime, timezone

        await self.event_manager.publish(
            self.run_id,
            {
                "type": "run_finished",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        await self.event_manager.close(self.run_id)
