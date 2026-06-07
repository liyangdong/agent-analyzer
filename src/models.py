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
