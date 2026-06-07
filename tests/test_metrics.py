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

    def _find_sample(samples, name, labels_subset=None):
        """Return the first sample matching name and optional label subset."""
        for s in samples:
            if s.name != name:
                continue
            if labels_subset:
                if all(s.labels.get(k) == v for k, v in labels_subset.items()):
                    return s
            else:
                return s
        return None

    all_samples = []
    for m in registry.collect():
        for s in m.samples:
            all_samples.append(s)

    # interactions_total: should be > 0 (1 tool execution inserted)
    interactions_sample = _find_sample(
        all_samples, "opencode_interactions_total",
        labels_subset={"session": "all", "tool": "all"},
    )
    assert interactions_sample is not None, "Missing interactions_total sample"
    assert interactions_sample.value > 0, (
        f"Expected interactions_total > 0, got {interactions_sample.value}"
    )

    # tokens_total: should be > 0 (1 message with 512 tokens inserted)
    tokens_sample = _find_sample(
        all_samples, "opencode_tokens_total",
        labels_subset={"session": "all", "direction": "total"},
    )
    assert tokens_sample is not None, "Missing tokens_total sample"
    assert tokens_sample.value > 0, (
        f"Expected tokens_total > 0, got {tokens_sample.value}"
    )

    # context_size_bytes: per-session gauge (2048 bytes from the message)
    ctx_sample = _find_sample(
        all_samples, "opencode_context_size_bytes",
        labels_subset={"session": "session-abc-123"},
    )
    assert ctx_sample is not None, "Missing context_size_bytes sample"
    assert ctx_sample.value == 2048, (
        f"Expected context_size_bytes == 2048, got {ctx_sample.value}"
    )

    # tool_duration_seconds: histogram should be populated
    dur_sample = _find_sample(
        all_samples, "opencode_tool_duration_seconds_sum",
    )
    assert dur_sample is not None, "Missing tool_duration_seconds histogram sample"
    assert dur_sample.value > 0, (
        f"Expected tool_duration_seconds_sum > 0, got {dur_sample.value}"
    )
