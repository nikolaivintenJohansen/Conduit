"""Unit tests for the usage-event queue (in-memory fallback path)."""

from __future__ import annotations

import pytest

from services.gateway import usage_queue


@pytest.fixture(autouse=True)
def _reset():
    usage_queue.reset_usage_queue()
    usage_queue.reset_idempotency()
    yield
    usage_queue.reset_usage_queue()
    usage_queue.reset_idempotency()


def test_enqueue_then_read_batch():
    usage_queue.ensure_consumer_group()
    id1 = usage_queue.enqueue_event({"request_id": "r1", "model": "gpt-4o-mini"})
    id2 = usage_queue.enqueue_event({"request_id": "r2", "model": "gpt-4o-mini"})

    batch = usage_queue.read_batch(consumer="test", count=10, block_ms=0)
    assert len(batch) == 2
    ids = [entry_id for entry_id, _ in batch]
    assert id1 in ids and id2 in ids
    assert batch[0][1]["request_id"] == "r1"


def test_ack_removes_from_pending():
    usage_queue.ensure_consumer_group()
    usage_queue.enqueue_event({"request_id": "r1", "model": "gpt-4o-mini"})
    batch = usage_queue.read_batch(consumer="test", count=10, block_ms=0)
    assert usage_queue.pending_count() == 1
    usage_queue.ack_event(batch[0][0])
    assert usage_queue.pending_count() == 0


def test_read_batch_returns_empty_when_no_events():
    usage_queue.ensure_consumer_group()
    assert usage_queue.read_batch(consumer="test", count=10, block_ms=0) == []


def test_mark_seen_is_idempotent():
    assert usage_queue.mark_seen("r1") is True
    assert usage_queue.mark_seen("r1") is False
    assert usage_queue.mark_seen("r2") is True


def test_stream_length_counts_pending_and_new():
    usage_queue.ensure_consumer_group()
    usage_queue.enqueue_event({"request_id": "r1", "model": "gpt-4o-mini"})
    usage_queue.enqueue_event({"request_id": "r2", "model": "gpt-4o-mini"})
    assert usage_queue.stream_length() == 2
    usage_queue.read_batch(consumer="test", count=1, block_ms=0)
    assert usage_queue.stream_length() == 2  # one new + one pending
