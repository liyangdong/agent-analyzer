# tests/test_ingest.py
import json
import os
import tempfile
import sqlite3
from src.models import init_db, get_session, get_recent_messages
from src.models import get_compactions_for_session, get_context_size
from src.ingest import parse_otlp_file, classify_event, process_event
from src.ingest import scan_directory, OTEL_EVENT_TYPES


def test_classify_tool_before(sample_tool_before):
    event_type = classify_event(sample_tool_before)
    assert event_type == OTEL_EVENT_TYPES["TOOL_BEFORE"]


def test_classify_tool_after(sample_tool_after):
    event_type = classify_event(sample_tool_after)
    assert event_type == OTEL_EVENT_TYPES["TOOL_AFTER"]


def test_classify_compacted(sample_compacted_event):
    event_type = classify_event(sample_compacted_event)
    assert event_type == OTEL_EVENT_TYPES["COMPACTED"]


def test_classify_message(sample_message_event):
    event_type = classify_event(sample_message_event)
    assert event_type == OTEL_EVENT_TYPES["MESSAGE"]


def test_classify_session_created():
    event = {"type": "session.created", "data": {}, "session_id": "s1", "timestamp": "t"}
    event_type = classify_event(event)
    assert event_type == OTEL_EVENT_TYPES["SESSION_CREATED"]


def test_classify_unknown():
    event = {"type": "weird.unknown.event", "data": {}, "session_id": "s1", "timestamp": "t"}
    event_type = classify_event(event)
    assert event_type == OTEL_EVENT_TYPES["UNKNOWN"]


def test_process_event_tool_after(temp_db, sample_session, sample_tool_after):
    init_db(temp_db)
    from src.models import insert_session
    insert_session(temp_db, sample_session)
    process_event(sample_tool_after, temp_db)
    conn = sqlite3.connect(temp_db)
    row = conn.execute("SELECT * FROM tool_executions").fetchone()
    assert row is not None
    conn.close()


def test_process_event_compacted(temp_db, sample_session, sample_compacted_event):
    init_db(temp_db)
    from src.models import insert_session
    insert_session(temp_db, sample_session)
    process_event(sample_compacted_event, temp_db, snapshot_message_count=5)
    compactions = get_compactions_for_session(temp_db, "session-abc-123")
    assert len(compactions) == 1
    assert compactions[0]["tokens_removed"] == 30000


def test_parse_otlp_file(temp_db, sample_tool_after, sample_message_event):
    init_db(temp_db)
    from src.models import insert_session
    insert_session(temp_db, {
        "id": "session-abc-123",
        "project": "test",
        "status": "active",
        "created_at": "2026-06-07T10:00:00Z",
        "updated_at": "2026-06-07T10:00:00Z",
    })
    events = [sample_tool_after, sample_message_event]
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(path, "w") as f:
        json.dump(events, f)
    count = parse_otlp_file(path, temp_db, snapshot_message_count=5,
                            expansion_threshold_pct=50)
    assert count == 2
    os.unlink(path)


def test_scan_directory(temp_db):
    init_db(temp_db)
    fd, path = tempfile.mkstemp(suffix=".json", dir=tempfile.gettempdir())
    os.close(fd)
    with open(path, "w") as f:
        json.dump([], f)
    count = scan_directory(tempfile.gettempdir(), temp_db, processed_cache=set())
    assert count >= 0
    os.unlink(path)
