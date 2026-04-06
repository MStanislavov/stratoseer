"""Unit tests for app.sse.RunEventManager."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from app.sse import RunEventManager


# ------------------------------------------------------------------
# subscribe / unsubscribe
# ------------------------------------------------------------------


class TestSubscribeUnsubscribe:
    """Tests for subscribe and unsubscribe mechanics."""

    async def test_subscribe_returns_queue(self):
        mgr = RunEventManager()
        queue = mgr.subscribe("run1")
        assert isinstance(queue, asyncio.Queue)

    async def test_subscribe_registers_queue(self):
        mgr = RunEventManager()
        queue = mgr.subscribe("run1")
        assert queue in mgr._queues["run1"]

    async def test_unsubscribe_removes_queue(self):
        mgr = RunEventManager()
        queue = mgr.subscribe("run1")
        assert len(mgr._queues["run1"]) == 1
        mgr.unsubscribe("run1", queue)
        assert len(mgr._queues["run1"]) == 0

    async def test_unsubscribe_nonexistent_run_noop(self):
        mgr = RunEventManager()
        queue = asyncio.Queue()
        # Should not raise
        mgr.unsubscribe("nonexistent", queue)

    async def test_unsubscribe_wrong_queue_noop(self):
        mgr = RunEventManager()
        q1 = mgr.subscribe("run1")
        q2 = asyncio.Queue()  # never subscribed
        mgr.unsubscribe("run1", q2)
        # q1 should still be registered
        assert q1 in mgr._queues["run1"]


# ------------------------------------------------------------------
# publish
# ------------------------------------------------------------------


class TestPublish:
    """Tests for the publish method."""

    async def test_publish_to_single_subscriber(self):
        mgr = RunEventManager()
        queue = mgr.subscribe("run1")
        await mgr.publish("run1", {"type": "test", "data": 1})
        event = queue.get_nowait()
        assert event == {"type": "test", "data": 1}

    async def test_publish_to_multiple_subscribers(self):
        mgr = RunEventManager()
        q1 = mgr.subscribe("run1")
        q2 = mgr.subscribe("run1")
        await mgr.publish("run1", {"type": "broadcast"})
        assert q1.get_nowait() == {"type": "broadcast"}
        assert q2.get_nowait() == {"type": "broadcast"}

    async def test_publish_stores_in_history(self):
        mgr = RunEventManager()
        mgr.subscribe("run1")
        await mgr.publish("run1", {"type": "first"})
        await mgr.publish("run1", {"type": "second"})
        assert len(mgr._history["run1"]) == 2

    async def test_publish_to_no_subscribers_still_stores_history(self):
        mgr = RunEventManager()
        await mgr.publish("run1", {"type": "orphan"})
        assert mgr._history["run1"] == [{"type": "orphan"}]

    async def test_publish_different_runs_isolated(self):
        mgr = RunEventManager()
        q1 = mgr.subscribe("run1")
        q2 = mgr.subscribe("run2")
        await mgr.publish("run1", {"type": "for_run1"})
        assert not q2.empty() is False or q2.qsize() == 0
        assert q1.get_nowait() == {"type": "for_run1"}
        assert q2.empty()


# ------------------------------------------------------------------
# history replay on subscribe
# ------------------------------------------------------------------


class TestHistoryReplay:
    """Tests that late subscribers get event history pre-filled."""

    async def test_new_subscriber_gets_history(self):
        mgr = RunEventManager()
        # Publish events before anyone subscribes
        await mgr.publish("run1", {"type": "event1"})
        await mgr.publish("run1", {"type": "event2"})
        # Subscribe late
        queue = mgr.subscribe("run1")
        assert queue.get_nowait() == {"type": "event1"}
        assert queue.get_nowait() == {"type": "event2"}

    async def test_new_subscriber_gets_history_and_live_events(self):
        mgr = RunEventManager()
        await mgr.publish("run1", {"type": "old"})
        queue = mgr.subscribe("run1")
        # History event
        assert queue.get_nowait() == {"type": "old"}
        # New live event
        await mgr.publish("run1", {"type": "live"})
        assert queue.get_nowait() == {"type": "live"}

    async def test_subscriber_to_closed_run_gets_history_and_sentinel(self):
        mgr = RunEventManager()
        await mgr.publish("run1", {"type": "done"})
        await mgr.close("run1")
        # Subscribe after close
        queue = mgr.subscribe("run1")
        assert queue.get_nowait() == {"type": "done"}
        assert queue.get_nowait() is None  # sentinel

    async def test_closed_run_subscriber_not_added_to_queues(self):
        mgr = RunEventManager()
        await mgr.close("run1")
        mgr.subscribe("run1")
        # Should not be registered in _queues since run is already closed
        assert "run1" not in mgr._queues


# ------------------------------------------------------------------
# close
# ------------------------------------------------------------------


class TestClose:
    """Tests for the close method."""

    async def test_close_sends_sentinel(self):
        mgr = RunEventManager()
        queue = mgr.subscribe("run1")
        await mgr.close("run1")
        sentinel = queue.get_nowait()
        assert sentinel is None

    async def test_close_marks_run_as_closed(self):
        mgr = RunEventManager()
        mgr.subscribe("run1")
        await mgr.close("run1")
        assert "run1" in mgr._closed

    async def test_close_removes_queues(self):
        mgr = RunEventManager()
        mgr.subscribe("run1")
        await mgr.close("run1")
        assert "run1" not in mgr._queues

    async def test_close_multiple_subscribers(self):
        mgr = RunEventManager()
        q1 = mgr.subscribe("run1")
        q2 = mgr.subscribe("run1")
        await mgr.close("run1")
        assert q1.get_nowait() is None
        assert q2.get_nowait() is None

    async def test_close_idempotent(self):
        mgr = RunEventManager()
        mgr.subscribe("run1")
        await mgr.close("run1")
        # Closing again should not raise
        await mgr.close("run1")
        assert "run1" in mgr._closed


# ------------------------------------------------------------------
# event_stream
# ------------------------------------------------------------------


class TestEventStream:
    """Tests for the async generator event_stream."""

    async def test_yields_events_as_sse_dicts(self):
        mgr = RunEventManager()
        # Publish some events, then close the run
        await mgr.publish("run1", {"type": "step", "n": 1})
        await mgr.publish("run1", {"type": "step", "n": 2})
        await mgr.close("run1")

        events = []
        async for event in mgr.event_stream("run1"):
            events.append(event)

        assert len(events) == 2
        assert events[0] == {"data": json.dumps({"type": "step", "n": 1})}
        assert events[1] == {"data": json.dumps({"type": "step", "n": 2})}

    async def test_stream_terminates_on_sentinel(self):
        mgr = RunEventManager()

        async def _producer():
            await mgr.publish("run1", {"type": "first"})
            await mgr.close("run1")

        # Start producer in background
        task = asyncio.create_task(_producer())
        events = []
        async for event in mgr.event_stream("run1"):
            events.append(event)
        await task

        assert len(events) == 1
        assert json.loads(events[0]["data"])["type"] == "first"

    async def test_stream_unsubscribes_on_exit(self):
        mgr = RunEventManager()
        await mgr.publish("run1", {"type": "a"})
        await mgr.close("run1")

        async for _ in mgr.event_stream("run1"):
            pass

        # After iteration the queue should be unsubscribed
        # Since run was closed, _queues["run1"] was already removed
        assert "run1" not in mgr._queues

    async def test_stream_with_live_events(self):
        mgr = RunEventManager()

        async def _producer():
            await asyncio.sleep(0.01)
            await mgr.publish("run1", {"type": "live1"})
            await asyncio.sleep(0.01)
            await mgr.publish("run1", {"type": "live2"})
            await asyncio.sleep(0.01)
            await mgr.close("run1")

        task = asyncio.create_task(_producer())
        events = []
        async for event in mgr.event_stream("run1"):
            events.append(event)
        await task

        assert len(events) == 2
        types = [json.loads(e["data"])["type"] for e in events]
        assert types == ["live1", "live2"]

    async def test_stream_replays_history_then_live(self):
        mgr = RunEventManager()
        # Pre-publish history
        await mgr.publish("run1", {"type": "historical"})

        async def _producer():
            await asyncio.sleep(0.01)
            await mgr.publish("run1", {"type": "live"})
            await asyncio.sleep(0.01)
            await mgr.close("run1")

        task = asyncio.create_task(_producer())
        events = []
        async for event in mgr.event_stream("run1"):
            events.append(event)
        await task

        assert len(events) == 2
        types = [json.loads(e["data"])["type"] for e in events]
        assert types == ["historical", "live"]


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------


class TestModuleSingleton:
    """Verify the module-level event_manager instance."""

    def test_module_level_instance_exists(self):
        from app.sse import event_manager

        assert isinstance(event_manager, RunEventManager)
