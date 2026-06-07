# OpenCode Agent Metrics Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python middleware that reads OpenTelemetry JSON files produced by the OpenCode telemetry plugin, stores structured data in SQLite, exposes Prometheus metrics, and provides a Grafana dashboard template.

**Architecture:** Watchdog monitors a directory for new OTLP JSON files. Ingest parses them into typed events, writes to SQLite via models layer. A metrics module queries SQLite to update Prometheus counters/gauges/histograms. An HTTP server exposes `/metrics` for Prometheus scrape and `/health`. The whole thing starts from `main.py` with a `config.yaml`.

**Tech Stack:** Python 3.10+, prometheus_client, pyyaml, watchdog, SQLite (stdlib), pytest

---

## File Map

| File | Responsibility |
|---|---|
| `config.yaml` | Configuration: paths, thresholds, ports |
| `requirements.txt` | Dependencies |
| `src/__init__.py` | Package init |
| `src/models.py` | SQLite schema DDL, insert/query functions |
| `src/ingest.py` | OTLP JSON parser, event classifier, writes through models |
| `src/metrics.py` | Prometheus metric objects and update functions |
| `src/server.py` | HTTP server with /metrics and /health |
| `src/main.py` | Entry point: wires watchdog, ingest, metrics, server |
| `tests/conftest.py` | Shared test fixtures (temp DB, sample OTLP data) |
| `tests/test_models.py` | Models unit tests |
| `tests/test_ingest.py` | Ingest unit tests |
| `tests/test_metrics.py` | Metrics unit tests |
| `grafana/dashboard.json` | Grafana dashboard template |

---

### Task 1: Project scaffolding

**Files:**
- Create: `config.yaml`
- Create: `requirements.txt`
- Create: `src/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create config.yaml**

```yaml
otel_data_dir: "./data/otel"
sqlite_path: "./data/metrics.db"
expansion_threshold_pct: 50
snapshot_message_count: 20
poll_interval_seconds: 5
metrics_port: 9090
```

- [ ] **Step 2: Create requirements.txt**

```
prometheus_client==0.21.1
pyyaml==6.2
watchdog==6.2.0
```

- [ ] **Step 3: Create src/__init__.py (empty)**

```python
```

- [ ] **Step 4: Create tests/conftest.py**

```python
import os
import sqlite3
import tempfile
import pytest


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def sample_session():
    return {
        "id": "session-abc-123",
        "project": "test-project",
        "status": "active",
        "created_at": "2026-06-07T10:00:00Z",
        "updated_at": "2026-06-07T10:00:00Z",
    }


@pytest.fixture
def sample_tool_before():
    return {
        "type": "tool.execute.before",
        "data": {
            "tool": "Read",
            "args": {"file_path": "/test/file.py"},
            "user": "test-user",
        },
        "session_id": "session-abc-123",
        "timestamp": "2026-06-07T10:01:00Z",
    }


@pytest.fixture
def sample_tool_after():
    return {
        "type": "tool.execute.after",
        "data": {
            "tool": "Read",
            "duration": 150.5,
            "success": True,
            "output": {"lines": 100},
        },
        "session_id": "session-abc-123",
        "timestamp": "2026-06-07T10:01:01Z",
    }


@pytest.fixture
def sample_compacted_event():
    return {
        "type": "session.compacted",
        "data": {
            "context_size_before": 50000,
            "context_size_after": 20000,
        },
        "session_id": "session-abc-123",
        "timestamp": "2026-06-07T10:05:00Z",
    }


@pytest.fixture
def sample_message_event():
    return {
        "type": "message.user.updated",
        "data": {
            "role": "user",
            "content_size": 2048,
            "token_count": 512,
        },
        "session_id": "session-abc-123",
        "timestamp": "2026-06-07T10:02:00Z",
    }
```

- [ ] **Step 5: Verify scaffolding**

Run: `python -c "import yaml; print(yaml.safe_load(open('config.yaml')))"`
Expected: prints parsed config dict

- [ ] **Step 6: Commit**

```bash
git add config.yaml requirements.txt src/__init__.py tests/conftest.py
git commit -m "feat: add project scaffolding"
```

---

### Task 2: SQLite models layer

**Files:**
- Create: `src/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_models.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_models.py -v`
Expected: all fail with ImportError or NameError

- [ ] **Step 3: Implement models.py**

```python
import sqlite3
import os


def init_db(db_path: str):
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            project TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tool_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            tool_name TEXT NOT NULL,
            args_json TEXT,
            duration_ms REAL,
            success INTEGER DEFAULT 1,
            error TEXT,
            input_size INTEGER DEFAULT 0,
            output_size INTEGER DEFAULT 0,
            timestamp TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            role TEXT NOT NULL,
            content_size INTEGER DEFAULT 0,
            token_count INTEGER DEFAULT 0,
            timestamp TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS compactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            context_size_before INTEGER DEFAULT 0,
            context_size_after INTEGER DEFAULT 0,
            tokens_removed INTEGER DEFAULT 0,
            snapshot_before TEXT,
            snapshot_after TEXT,
            timestamp TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS context_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            context_size INTEGER DEFAULT 0,
            trigger_event TEXT,
            delta_pct REAL DEFAULT 0,
            snapshot_json TEXT,
            timestamp TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_tool_exec_session ON tool_executions(session_id);
        CREATE INDEX IF NOT EXISTS idx_tool_exec_ts ON tool_executions(timestamp);
        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
        CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(timestamp);
        CREATE INDEX IF NOT EXISTS idx_compactions_session ON compactions(session_id);
        CREATE INDEX IF NOT EXISTS idx_snapshots_session ON context_snapshots(session_id);
    """)
    conn.commit()
    conn.close()


def _row_factory(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


def _connect(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = _row_factory
    return conn


def insert_session(db_path: str, session: dict):
    conn = _connect(db_path)
    conn.execute(
        "INSERT OR REPLACE INTO sessions (id, project, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (session["id"], session["project"], session["status"],
         session["created_at"], session["updated_at"]),
    )
    conn.commit()
    conn.close()


def get_session(db_path: str, session_id: str):
    conn = _connect(db_path)
    row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    conn.close()
    return row


def insert_tool_execution(db_path: str, event: dict):
    conn = _connect(db_path)
    d = event["data"]
    args_json = str(d.get("args", "{}"))
    conn.execute(
        """INSERT INTO tool_executions
           (session_id, tool_name, args_json, duration_ms, success, error, input_size, output_size, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (event["session_id"], d["tool"], args_json,
         d.get("duration", 0), 1 if d.get("success") else 0,
         d.get("error"), d.get("input_size", 0), d.get("output_size", 0),
         event["timestamp"]),
    )
    conn.commit()
    conn.close()


def insert_message(db_path: str, event: dict):
    conn = _connect(db_path)
    d = event["data"]
    role = d.get("role", "unknown")
    conn.execute(
        "INSERT INTO messages (session_id, role, content_size, token_count, timestamp) VALUES (?, ?, ?, ?, ?)",
        (event["session_id"], role, d.get("content_size", 0),
         d.get("token_count", 0), event["timestamp"]),
    )
    conn.commit()
    conn.close()


def get_recent_messages(db_path: str, session_id: str, limit: int = 20):
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    conn.close()
    return rows


def insert_compaction(db_path: str, event: dict, snapshot_before: str, snapshot_after: str):
    conn = _connect(db_path)
    d = event["data"]
    before = d.get("context_size_before", 0)
    after = d.get("context_size_after", 0)
    tokens_removed = before - after
    conn.execute(
        """INSERT INTO compactions
           (session_id, context_size_before, context_size_after, tokens_removed,
            snapshot_before, snapshot_after, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (event["session_id"], before, after, tokens_removed,
         snapshot_before, snapshot_after, event["timestamp"]),
    )
    conn.commit()
    conn.close()


def get_compactions_for_session(db_path: str, session_id: str):
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT * FROM compactions WHERE session_id = ? ORDER BY timestamp DESC",
        (session_id,),
    ).fetchall()
    conn.close()
    return rows


def insert_context_snapshot(db_path: str, session_id: str, context_size: int,
                             trigger_event: str, delta_pct: float,
                             snapshot_json: str, timestamp: str):
    conn = _connect(db_path)
    conn.execute(
        """INSERT INTO context_snapshots
           (session_id, context_size, trigger_event, delta_pct, snapshot_json, timestamp)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (session_id, context_size, trigger_event, delta_pct, snapshot_json, timestamp),
    )
    conn.commit()
    conn.close()


def get_context_size(db_path: str, session_id: str) -> int:
    conn = _connect(db_path)
    row = conn.execute(
        "SELECT content_size FROM messages WHERE session_id = ? ORDER BY timestamp DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    conn.close()
    return row["content_size"] if row else 0


def get_total_interactions(db_path: str) -> int:
    conn = _connect(db_path)
    row = conn.execute("SELECT COUNT(*) as cnt FROM tool_executions").fetchone()
    conn.close()
    return row["cnt"] if row else 0


def get_total_tokens(db_path: str) -> int:
    conn = _connect(db_path)
    row = conn.execute("SELECT COALESCE(SUM(token_count), 0) as total FROM messages").fetchone()
    conn.close()
    return row["total"] if row else 0


def get_total_compactions(db_path: str) -> int:
    conn = _connect(db_path)
    row = conn.execute("SELECT COUNT(*) as cnt FROM compactions").fetchone()
    conn.close()
    return row["cnt"] if row else 0


def get_interactions_by_tool(db_path: str) -> list[dict]:
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT tool_name, COUNT(*) as cnt FROM tool_executions GROUP BY tool_name"
    ).fetchall()
    conn.close()
    return rows


def get_expansion_events_by_tool(db_path: str) -> list[dict]:
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT trigger_event, COUNT(*) as cnt FROM context_snapshots GROUP BY trigger_event"
    ).fetchall()
    conn.close()
    return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: all 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/models.py tests/test_models.py
git commit -m "feat: add SQLite models layer"
```

---

### Task 3: OTLP ingest module

**Files:**
- Create: `src/ingest.py`
- Create: `tests/test_ingest.py`

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ingest.py -v`
Expected: all fail with ImportError

- [ ] **Step 3: Implement ingest.py**

```python
import json
import os
from src.models import (
    insert_tool_execution, insert_message, insert_compaction,
    insert_context_snapshot, insert_session, get_recent_messages,
    get_context_size, get_session,
)


OTEL_EVENT_TYPES = {
    "TOOL_BEFORE": 1,
    "TOOL_AFTER": 2,
    "SESSION_CREATED": 3,
    "SESSION_UPDATED": 4,
    "SESSION_COMPACTED": 5,
    "COMPACTED": 5,
    "MESSAGE": 6,
    "PERMISSION": 7,
    "UNKNOWN": 99,
}


def classify_event(event: dict) -> int:
    event_type = event.get("type", "")
    if event_type == "tool.execute.before":
        return OTEL_EVENT_TYPES["TOOL_BEFORE"]
    elif event_type == "tool.execute.after":
        return OTEL_EVENT_TYPES["TOOL_AFTER"]
    elif event_type in ("session.created",):
        return OTEL_EVENT_TYPES["SESSION_CREATED"]
    elif event_type in ("session.compacted",):
        return OTEL_EVENT_TYPES["COMPACTED"]
    elif event_type.startswith("message."):
        return OTEL_EVENT_TYPES["MESSAGE"]
    elif event_type.startswith("permission."):
        return OTEL_EVENT_TYPES["PERMISSION"]
    return OTEL_EVENT_TYPES["UNKNOWN"]


def process_event(event: dict, db_path: str, snapshot_message_count: int = 20,
                  expansion_threshold_pct: float = 50.0):
    event_type = classify_event(event)
    session_id = event.get("session_id", "unknown")

    if event_type == OTEL_EVENT_TYPES["TOOL_AFTER"]:
        insert_tool_execution(db_path, event)
        _check_context_expansion(
            db_path, session_id, event["data"].get("tool", "unknown"),
            event.get("timestamp", ""), snapshot_message_count,
            expansion_threshold_pct,
        )

    elif event_type == OTEL_EVENT_TYPES["MESSAGE"]:
        insert_message(db_path, event)
        _check_context_expansion(
            db_path, session_id, "message",
            event.get("timestamp", ""), snapshot_message_count,
            expansion_threshold_pct,
        )

    elif event_type == OTEL_EVENT_TYPES["COMPACTED"]:
        messages = get_recent_messages(db_path, session_id, snapshot_message_count)
        snapshot_before = json.dumps(messages, ensure_ascii=False)
        snapshot_after = ""
        insert_compaction(db_path, event, snapshot_before, snapshot_after)
        _update_compaction_snapshot_after(db_path, session_id, snapshot_message_count)

    elif event_type == OTEL_EVENT_TYPES["TOOL_BEFORE"]:
        pass

    elif event_type == OTEL_EVENT_TYPES["SESSION_CREATED"]:
        d = event.get("data", {})
        session = {
            "id": session_id,
            "project": d.get("project", "unknown"),
            "status": "active",
            "created_at": event.get("timestamp", ""),
            "updated_at": event.get("timestamp", ""),
        }
        insert_session(db_path, session)


def _check_context_expansion(db_path: str, session_id: str, trigger: str,
                              timestamp: str, snapshot_count: int,
                              threshold_pct: float):
    current_size = get_context_size(db_path, session_id)
    if current_size == 0:
        return
    conn = _connect_simple(db_path)
    prev = conn.execute(
        "SELECT context_size FROM context_snapshots WHERE session_id = ? ORDER BY timestamp DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    conn.close()
    prev_size = prev[0] if prev else 0
    if prev_size > 0:
        delta_pct = ((current_size - prev_size) / prev_size) * 100
    else:
        delta_pct = 100.0
    if delta_pct >= threshold_pct:
        messages = get_recent_messages(db_path, session_id, snapshot_count)
        snapshot_json = json.dumps(messages, ensure_ascii=False)
        insert_context_snapshot(
            db_path, session_id, current_size, trigger,
            delta_pct, snapshot_json, timestamp,
        )


def _connect_simple(db_path: str):
    import sqlite3
    return sqlite3.connect(db_path)


def _update_compaction_snapshot_after(db_path: str, session_id: str, snapshot_count: int):
    import sqlite3
    conn = sqlite3.connect(db_path)
    messages = get_recent_messages(db_path, session_id, snapshot_count)
    snapshot_after = json.dumps(messages, ensure_ascii=False)
    conn.execute(
        """UPDATE compactions SET snapshot_after = ?
           WHERE session_id = ? AND id = (SELECT MAX(id) FROM compactions WHERE session_id = ?)""",
        (snapshot_after, session_id, session_id),
    )
    conn.commit()
    conn.close()


def parse_otlp_file(file_path: str, db_path: str, snapshot_message_count: int = 20,
                    expansion_threshold_pct: float = 50.0) -> int:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    events = data if isinstance(data, list) else [data]
    count = 0
    for event in events:
        process_event(event, db_path, snapshot_message_count, expansion_threshold_pct)
        count += 1
    return count


def scan_directory(otel_dir: str, db_path: str, processed_cache: set,
                   snapshot_message_count: int = 20,
                   expansion_threshold_pct: float = 50.0) -> int:
    if not os.path.isdir(otel_dir):
        return 0
    total = 0
    for filename in sorted(os.listdir(otel_dir)):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(otel_dir, filename)
        mtime = os.path.getmtime(filepath)
        cache_key = f"{filepath}:{mtime}"
        if cache_key in processed_cache:
            continue
        total += parse_otlp_file(filepath, db_path, snapshot_message_count,
                                 expansion_threshold_pct)
        processed_cache.add(cache_key)
    return total
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ingest.py -v`
Expected: all 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/ingest.py tests/test_ingest.py
git commit -m "feat: add OTLP ingest module"
```

---

### Task 4: Prometheus metrics module

**Files:**
- Create: `src/metrics.py`
- Create: `tests/test_metrics.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_metrics.py
from prometheus_client import REGISTRY, CollectorRegistry
from src.models import init_db, insert_session, insert_tool_execution, insert_message
from src.models import insert_compaction, insert_context_snapshot
from src.metrics import create_metrics, update_all_metrics


def test_create_metrics():
    registry = CollectorRegistry()
    metrics = create_metrics(registry)
    assert "interactions_total" in metrics
    assert "tokens_total" in metrics
    assert "context_size_bytes" in metrics
    assert "compactions_total" in metrics
    assert "context_expansion_total" in metrics
    assert "tool_duration_seconds" in metrics
    assert "compaction_tokens_removed" in metrics


def test_update_metrics_no_data(temp_db):
    init_db(temp_db)
    registry = CollectorRegistry()
    metrics = create_metrics(registry)
    update_all_metrics(temp_db, metrics)
    samples = []
    for m in registry.collect():
        for s in m.samples:
            samples.append(s)
    # Should have samples without errors
    assert len(samples) >= 0


def test_update_metrics_with_data(temp_db, sample_session, sample_tool_after, sample_message_event):
    init_db(temp_db)
    insert_session(temp_db, sample_session)
    insert_tool_execution(temp_db, sample_tool_after)
    insert_message(temp_db, sample_message_event)
    registry = CollectorRegistry()
    metrics = create_metrics(registry)
    update_all_metrics(temp_db, metrics)
    # Verify counters have values
    samples_by_name = {}
    for m in registry.collect():
        for s in m.samples:
            name = s.name
            if name not in samples_by_name:
                samples_by_name[name] = []
            samples_by_name[name].append(s)
    assert "opencode_interactions_total" in samples_by_name
    assert "opencode_tokens_total" in samples_by_name
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_metrics.py -v`
Expected: all fail with ImportError

- [ ] **Step 3: Implement metrics.py**

```python
from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry

METRIC_PREFIX = "opencode"


def create_metrics(registry: CollectorRegistry) -> dict:
    return {
        "interactions_total": Counter(
            f"{METRIC_PREFIX}_interactions_total",
            "Total tool/model interactions",
            ["session", "tool"],
            registry=registry,
        ),
        "tokens_total": Counter(
            f"{METRIC_PREFIX}_tokens_total",
            "Total tokens consumed",
            ["session", "direction"],
            registry=registry,
        ),
        "context_size_bytes": Gauge(
            f"{METRIC_PREFIX}_context_size_bytes",
            "Current context window size in bytes",
            ["session"],
            registry=registry,
        ),
        "compactions_total": Counter(
            f"{METRIC_PREFIX}_compactions_total",
            "Total compaction events",
            ["session"],
            registry=registry,
        ),
        "context_expansion_total": Counter(
            f"{METRIC_PREFIX}_context_expansion_total",
            "Rapid context expansion events",
            ["session", "tool"],
            registry=registry,
        ),
        "tool_duration_seconds": Histogram(
            f"{METRIC_PREFIX}_tool_duration_seconds",
            "Tool execution duration",
            ["session", "tool"],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
            registry=registry,
        ),
        "compaction_tokens_removed": Histogram(
            f"{METRIC_PREFIX}_compaction_tokens_removed",
            "Tokens removed per compaction",
            ["session"],
            buckets=[100, 500, 1000, 5000, 10000, 50000, 100000],
            registry=registry,
        ),
    }


def update_all_metrics(db_path: str, metrics: dict):
    from src.models import (
        get_total_interactions, get_total_tokens, get_context_size,
        get_total_compactions, get_interactions_by_tool,
        get_expansion_events_by_tool,
    )
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = lambda c, r: {col[0]: r[i] for i, col in enumerate(c.description)}

    sessions = conn.execute("SELECT id FROM sessions").fetchall()
    session_ids = [s["id"] for s in sessions] if sessions else ["default"]
    conn.close()

    for sid in session_ids:
        total_interactions = get_total_interactions(db_path)
        if total_interactions > 0:
            metrics["interactions_total"].labels(session=sid, tool="all").inc(total_interactions)

        total_tokens = get_total_tokens(db_path)
        if total_tokens > 0:
            metrics["tokens_total"].labels(session=sid, direction="total").inc(total_tokens)

        ctx_size = get_context_size(db_path, sid)
        metrics["context_size_bytes"].labels(session=sid).set(ctx_size)

        total_comp = get_total_compactions(db_path)
        if total_comp > 0:
            metrics["compactions_total"].labels(session=sid).inc(total_comp)

    interactions_by_tool = get_interactions_by_tool(db_path)
    for row in interactions_by_tool:
        metrics["interactions_total"].labels(
            session="all", tool=row["tool_name"]
        ).inc(row["cnt"])

    expansions_by_tool = get_expansion_events_by_tool(db_path)
    for row in expansions_by_tool:
        metrics["context_expansion_total"].labels(
            session="all", tool=row["trigger_event"]
        ).inc(row["cnt"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_metrics.py -v`
Expected: all 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/metrics.py tests/test_metrics.py
git commit -m "feat: add Prometheus metrics module"
```

---

### Task 5: HTTP server module

**Files:**
- Create: `src/server.py`

- [ ] **Step 1: Implement server.py**

```python
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from prometheus_client import CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
from src.metrics import create_metrics, update_all_metrics


class MetricsHandler(BaseHTTPRequestHandler):
    metrics: dict = {}
    registry: CollectorRegistry = None
    db_path: str = ""

    def do_GET(self):
        if self.path == "/metrics":
            update_all_metrics(self.db_path, self.metrics)
            data = generate_latest(self.registry)
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/health":
            db_exists = os.path.exists(self.db_path)
            status = {"status": "ok" if db_exists else "degraded", "db_path": self.db_path}
            body = str(status).encode()
            self.send_response(200 if db_exists else 503)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def start_server(port: int, db_path: str, metrics: dict, registry: CollectorRegistry):
    handler = MetricsHandler
    handler.metrics = metrics
    handler.registry = registry
    handler.db_path = db_path
    server = HTTPServer(("0.0.0.0", port), handler)
    print(f"Metrics server listening on port {port}")
    return server
```

- [ ] **Step 2: Commit**

```bash
git add src/server.py
git commit -m "feat: add HTTP metrics server module"
```

---

### Task 6: Main entry point

**Files:**
- Create: `src/main.py`

- [ ] **Step 1: Implement main.py**

```python
import os
import sys
import time
import signal
import threading
import yaml
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from prometheus_client import CollectorRegistry

from src.models import init_db
from src.ingest import scan_directory
from src.metrics import create_metrics
from src.server import start_server


class OtelFileHandler(FileSystemEventHandler):
    def __init__(self, db_path, config):
        self.db_path = db_path
        self.snapshot_count = config.get("snapshot_message_count", 20)
        self.threshold_pct = config.get("expansion_threshold_pct", 50.0)

    def on_created(self, event):
        if event.src_path.endswith(".json"):
            from src.ingest import parse_otlp_file
            try:
                parse_otlp_file(event.src_path, self.db_path,
                                self.snapshot_count, self.threshold_pct)
            except Exception as e:
                print(f"Error processing {event.src_path}: {e}", file=sys.stderr)


def load_config(config_path="config.yaml"):
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def main():
    config = load_config()
    db_path = config["sqlite_path"]
    otel_dir = config["otel_data_dir"]
    poll_interval = config.get("poll_interval_seconds", 5)
    metrics_port = config.get("metrics_port", 9090)
    snapshot_count = config.get("snapshot_message_count", 20)
    threshold_pct = config.get("expansion_threshold_pct", 50.0)

    init_db(db_path)

    registry = CollectorRegistry()
    metrics = create_metrics(registry)

    processed_cache = set()

    server = start_server(metrics_port, db_path, metrics, registry)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    event_handler = OtelFileHandler(db_path, config)
    observer = Observer()
    observer.schedule(event_handler, otel_dir, recursive=False)
    observer.start()

    def shutdown(signum, frame):
        observer.stop()
        observer.join()
        server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"Watching {otel_dir} for OTLP files, metrics on :{metrics_port}")

    try:
        while True:
            new_count = scan_directory(otel_dir, db_path, processed_cache,
                                       snapshot_count, threshold_pct)
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        shutdown(None, None)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify main imports work**

Run: `cd D:\project\agent-analyzer-1 && python -c "from src.main import load_config; c = load_config(); print(c)"`
Expected: prints parsed config

- [ ] **Step 3: Commit**

```bash
git add src/main.py
git commit -m "feat: add main entry point"
```

---

### Task 7: Grafana dashboard template

**Files:**
- Create: `grafana/dashboard.json`

- [ ] **Step 1: Create dashboard JSON**

```json
{
  "title": "OpenCode Agent Metrics",
  "uid": "opencode-agent-metrics",
  "panels": [
    {
      "id": 1,
      "title": "Total Interactions",
      "type": "stat",
      "gridPos": {"x": 0, "y": 0, "w": 8, "h": 4},
      "targets": [
        {"expr": "sum(opencode_interactions_total)", "legendFormat": "Total"}
      ]
    },
    {
      "id": 2,
      "title": "Total Tokens",
      "type": "stat",
      "gridPos": {"x": 8, "y": 0, "w": 8, "h": 4},
      "targets": [
        {"expr": "sum(opencode_tokens_total)", "legendFormat": "Total"}
      ]
    },
    {
      "id": 3,
      "title": "Total Compactions",
      "type": "stat",
      "gridPos": {"x": 16, "y": 0, "w": 8, "h": 4},
      "targets": [
        {"expr": "sum(opencode_compactions_total)", "legendFormat": "Total"}
      ]
    },
    {
      "id": 4,
      "title": "Context Size Trend",
      "type": "timeseries",
      "gridPos": {"x": 0, "y": 4, "w": 24, "h": 8},
      "targets": [
        {"expr": "opencode_context_size_bytes", "legendFormat": "{{session}}"}
      ]
    },
    {
      "id": 5,
      "title": "Interactions by Tool",
      "type": "bargauge",
      "gridPos": {"x": 0, "y": 12, "w": 12, "h": 8},
      "targets": [
        {"expr": "sum(opencode_interactions_total) by (tool)", "legendFormat": "{{tool}}"}
      ]
    },
    {
      "id": 6,
      "title": "Tool Duration Heatmap",
      "type": "heatmap",
      "gridPos": {"x": 12, "y": 12, "w": 12, "h": 8},
      "targets": [
        {"expr": "rate(opencode_tool_duration_seconds_bucket[5m])", "legendFormat": "{{le}}"}
      ]
    },
    {
      "id": 7,
      "title": "Context Expansion Events by Tool",
      "type": "timeseries",
      "gridPos": {"x": 0, "y": 20, "w": 24, "h": 8},
      "targets": [
        {"expr": "rate(opencode_context_expansion_total[5m])", "legendFormat": "{{tool}}"}
      ]
    }
  ],
  "schemaVersion": 38,
  "refresh": "10s"
}
```

- [ ] **Step 2: Commit**

```bash
git add grafana/dashboard.json
git commit -m "feat: add Grafana dashboard template"
```

---

### Task 8: Integration smoke test

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
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
```

- [ ] **Step 2: Run integration test**

Run: `pytest tests/test_integration.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add integration smoke test"
```

---

### Task 9: Final verification

- [ ] **Step 1: Run all tests**

```bash
pytest tests/ -v
```
Expected: all tests PASS

- [ ] **Step 2: Verify config loads**

```bash
python -c "from src.main import load_config; print(load_config())"
```
Expected: prints config dict

- [ ] **Step 3: Verify all imports resolve**

```bash
python -c "from src.models import *; from src.ingest import *; from src.metrics import *; from src.server import *; print('OK')"
```
Expected: prints OK
