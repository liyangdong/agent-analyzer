import sqlite3
from src.models import init_db, insert_session, get_session, insert_tool_execution
from src.models import insert_message, insert_compaction, insert_context_snapshot
from src.models import get_recent_messages, get_context_size, get_compactions_for_session


def test_init_db_creates_tables(temp_db):
    init_db(temp_db)
    conn = sqlite3.connect(temp_db)
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = [t[0] for t in tables]
    assert "sessions" in table_names
    assert "tool_executions" in table_names
    assert "messages" in table_names
    assert "compactions" in table_names
    assert "context_snapshots" in table_names
    conn.close()


def test_insert_and_get_session(temp_db, sample_session):
    init_db(temp_db)
    insert_session(temp_db, sample_session)
    result = get_session(temp_db, "session-abc-123")
    assert result["id"] == "session-abc-123"
    assert result["project"] == "test-project"
    assert result["status"] == "active"


def test_insert_tool_execution(temp_db, sample_session, sample_tool_after):
    init_db(temp_db)
    insert_session(temp_db, sample_session)
    insert_tool_execution(temp_db, sample_tool_after)
    conn = sqlite3.connect(temp_db)
    row = conn.execute("SELECT * FROM tool_executions").fetchone()
    assert row is not None
    conn.close()


def test_insert_message_and_get_recent(temp_db, sample_session, sample_message_event):
    init_db(temp_db)
    insert_session(temp_db, sample_session)
    insert_message(temp_db, sample_message_event)
    messages = get_recent_messages(temp_db, "session-abc-123", limit=10)
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["token_count"] == 512


def test_insert_compaction_and_query(temp_db, sample_session, sample_compacted_event):
    init_db(temp_db)
    insert_session(temp_db, sample_session)
    insert_compaction(temp_db, sample_compacted_event, "before snap", "after snap")
    compactions = get_compactions_for_session(temp_db, "session-abc-123")
    assert len(compactions) == 1
    assert compactions[0]["tokens_removed"] == 30000
    assert compactions[0]["snapshot_before"] == "before snap"
    assert compactions[0]["snapshot_after"] == "after snap"


def test_insert_context_snapshot(temp_db, sample_session):
    init_db(temp_db)
    insert_session(temp_db, sample_session)
    insert_context_snapshot(
        temp_db,
        session_id="session-abc-123",
        context_size=60000,
        trigger_event="Read",
        delta_pct=75.0,
        snapshot_json='{"messages":[]}',
        timestamp="2026-06-07T10:03:00Z",
    )
    conn = sqlite3.connect(temp_db)
    row = conn.execute("SELECT * FROM context_snapshots").fetchone()
    assert row is not None
    conn.close()


def test_get_context_size_returns_latest(temp_db, sample_session, sample_message_event):
    init_db(temp_db)
    insert_session(temp_db, sample_session)
    insert_message(temp_db, sample_message_event)
    size = get_context_size(temp_db, "session-abc-123")
    assert size == 2048
