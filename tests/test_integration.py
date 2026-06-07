# tests/test_integration.py
import json
import os
import tempfile
from src.models import init_db
from src.ingest import parse_otlp_file
from src.metrics import create_metrics, update_all_metrics
from prometheus_client import CollectorRegistry


def test_full_pipeline(temp_db):
    init_db(temp_db)
    event = {
        "type": "tool.execute.after",
        "data": {
            "tool": "Bash",
            "duration": 200.0,
            "success": True,
            "output_size": 4096,
        },
        "session_id": "session-xyz",
        "timestamp": "2026-06-07T12:00:00Z",
    }
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(path, "w") as f:
        json.dump([event], f)

    from src.models import insert_session
    insert_session(temp_db, {
        "id": "session-xyz",
        "project": "test",
        "status": "active",
        "created_at": "2026-06-07T12:00:00Z",
        "updated_at": "2026-06-07T12:00:00Z",
    })

    count = parse_otlp_file(path, temp_db, snapshot_message_count=20,
                            expansion_threshold_pct=50)
    assert count == 1

    import sqlite3
    conn = sqlite3.connect(temp_db)
    row = conn.execute("SELECT * FROM tool_executions WHERE session_id = 'session-xyz'").fetchone()
    assert row is not None
    conn.close()

    registry = CollectorRegistry()
    metrics = create_metrics(registry)
    update_all_metrics(temp_db, metrics)
    samples = list(registry.collect())
    assert len(samples) > 0

    os.unlink(path)
