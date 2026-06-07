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
        get_expansion_events_by_tool, _connect,
    )

    with _connect(db_path) as conn:
        sessions = conn.execute("SELECT id FROM sessions").fetchall()
    session_ids = [s["id"] for s in sessions] if sessions else ["default"]

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
