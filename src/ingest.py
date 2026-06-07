import json
import os
from src.models import (
    insert_tool_execution, insert_message, insert_compaction,
    insert_context_snapshot, insert_session, get_recent_messages,
    get_context_size, get_session, _connect,
)


OTEL_EVENT_TYPES = {
    "TOOL_BEFORE": 1,
    "TOOL_AFTER": 2,
    "SESSION_CREATED": 3,
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
    with _connect(db_path) as conn:
        prev = conn.execute(
            "SELECT context_size FROM context_snapshots WHERE session_id = ? ORDER BY timestamp DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        prev_size = prev["context_size"] if prev else 0
    if prev_size > 0:
        delta_pct = ((current_size - prev_size) / prev_size) * 100
    else:
        delta_pct = 100.0
    if delta_pct >= threshold_pct:
        messages = get_recent_messages(db_path, session_id, snapshot_count)
        snapshot_json = json.dumps(messages, ensure_ascii=False)
        insert_context_snapshot(
            db_path, session_id=session_id, context_size=current_size,
            trigger_event=trigger, delta_pct=delta_pct,
            snapshot_json=snapshot_json, timestamp=timestamp,
        )


def _update_compaction_snapshot_after(db_path: str, session_id: str, snapshot_count: int):
    messages = get_recent_messages(db_path, session_id, snapshot_count)
    snapshot_after = json.dumps(messages, ensure_ascii=False)
    with _connect(db_path) as conn:
        conn.execute(
            """UPDATE compactions SET snapshot_after = ?
               WHERE session_id = ? AND id = (SELECT MAX(id) FROM compactions WHERE session_id = ?)""",
            (snapshot_after, session_id, session_id),
        )
        conn.commit()


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
