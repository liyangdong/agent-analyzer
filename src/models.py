import json
import sqlite3
import os
from contextlib import contextmanager


def init_db(db_path: str):
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    with _connect(db_path) as conn:
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


def _row_factory(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


@contextmanager
def _connect(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = _row_factory
    try:
        yield conn
    finally:
        conn.close()


def insert_session(db_path: str, session: dict):
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO sessions (id, project, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (session["id"], session["project"], session["status"],
             session["created_at"], session["updated_at"]),
        )
        conn.commit()


def get_session(db_path: str, session_id: str):
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return row


def insert_tool_execution(db_path: str, event: dict):
    with _connect(db_path) as conn:
        d = event["data"]
        args_json = json.dumps(d.get("args", {}))
        conn.execute(
            """INSERT INTO tool_executions
               (session_id, tool_name, args_json, duration_ms, success, error, input_size, output_size, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event["session_id"], d["tool"], args_json,
             d.get("duration", 0), 1 if d.get("success", True) else 0,
             d.get("error"), d.get("input_size", 0), d.get("output_size", 0),
             event["timestamp"]),
        )
        conn.commit()


def insert_message(db_path: str, event: dict):
    with _connect(db_path) as conn:
        d = event["data"]
        role = d.get("role", "unknown")
        conn.execute(
            "INSERT INTO messages (session_id, role, content_size, token_count, timestamp) VALUES (?, ?, ?, ?, ?)",
            (event["session_id"], role, d.get("content_size", 0),
             d.get("token_count", 0), event["timestamp"]),
        )
        conn.commit()


def get_recent_messages(db_path: str, session_id: str, limit: int = 20):
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return rows


def insert_compaction(db_path: str, event: dict, snapshot_before: str, snapshot_after: str):
    with _connect(db_path) as conn:
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


def get_compactions_for_session(db_path: str, session_id: str):
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM compactions WHERE session_id = ? ORDER BY timestamp DESC",
            (session_id,),
        ).fetchall()
    return rows


def insert_context_snapshot(db_path: str, *, session_id: str, context_size: int,
                             trigger_event: str, delta_pct: float,
                             snapshot_json: str, timestamp: str):
    with _connect(db_path) as conn:
        conn.execute(
            """INSERT INTO context_snapshots
               (session_id, context_size, trigger_event, delta_pct, snapshot_json, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, context_size, trigger_event, delta_pct, snapshot_json, timestamp),
        )
        conn.commit()


def get_context_size(db_path: str, session_id: str) -> int:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(content_size), 0) as total FROM messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return row["total"] if row else 0


def get_total_interactions(db_path: str) -> int:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) as cnt FROM tool_executions").fetchone()
    return row["cnt"] if row else 0


def get_total_tokens(db_path: str) -> int:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT COALESCE(SUM(token_count), 0) as total FROM messages").fetchone()
    return row["total"] if row else 0


def get_total_compactions(db_path: str) -> int:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) as cnt FROM compactions").fetchone()
    return row["cnt"] if row else 0


def get_interactions_by_tool(db_path: str) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT tool_name, COUNT(*) as cnt FROM tool_executions GROUP BY tool_name"
        ).fetchall()
    return rows


def get_expansion_events_by_tool(db_path: str) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT trigger_event, COUNT(*) as cnt FROM context_snapshots GROUP BY trigger_event"
        ).fetchall()
    return rows


def get_tool_durations(db_path: str) -> list[dict]:
    with _connect(db_path) as conn:
        return conn.execute(
            "SELECT session_id, tool_name, duration_ms FROM tool_executions WHERE duration_ms IS NOT NULL"
        ).fetchall()


def get_compaction_tokens_removed(db_path: str) -> list[dict]:
    with _connect(db_path) as conn:
        return conn.execute(
            "SELECT session_id, tokens_removed FROM compactions WHERE tokens_removed IS NOT NULL"
        ).fetchall()
