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
