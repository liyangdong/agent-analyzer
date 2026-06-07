# OpenCode Agent Metrics Dashboard — Design Spec

## Overview

An OpenTelemetry-based metrics pipeline for OpenCode AI agents:
OpenCode Telemetry Plugin → OTLP local files → Python middleware (SQLite + Prometheus exporter) → Prometheus → Grafana.

## Goals

1. Track interactions per development task (tool calls, message rounds)
2. Track token consumption (input/output)
3. Context size trend over time
4. Compaction event count and before/after snapshots
5. Identify which tool actions trigger rapid context expansion
6. Context snapshots at expansion points

## Architecture

```
OpenCode (telemetry plugin)
    │  OTLP JSON files
    ▼
Python Middleware
 ├── ingest.py   — parse OTLP, classify events, write SQLite
 ├── models.py   — schema DDL, CRUD queries
 ├── metrics.py  — Prometheus counters/gauges/histograms
 └── server.py   — HTTP /metrics (Prometheus scrape), /health
    │  /metrics endpoint
    ▼
Prometheus
    │
    ▼
Grafana (dashboard JSON provided)
```

## Data Model (SQLite)

### sessions
| Column | Type | Notes |
|---|---|---|
| id | TEXT PK | session UUID |
| project | TEXT | project name |
| status | TEXT | active/idle/error/terminated |
| created_at | TEXT | ISO8601 |
| updated_at | TEXT | ISO8601 |

### tool_executions
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | autoincrement |
| session_id | TEXT FK | references sessions.id |
| tool_name | TEXT | Read, Edit, Bash, etc. |
| args_json | TEXT | arguments snapshot |
| duration_ms | REAL | execution time |
| success | INTEGER | 0 or 1 |
| error | TEXT | nullable |
| input_size | INTEGER | bytes |
| output_size | INTEGER | bytes |
| timestamp | TEXT | ISO8601 |

### messages
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | autoincrement |
| session_id | TEXT FK | references sessions.id |
| role | TEXT | user/assistant/system |
| content_size | INTEGER | bytes |
| token_count | INTEGER | estimated tokens |
| timestamp | TEXT | ISO8601 |

### compactions
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | autoincrement |
| session_id | TEXT FK | |
| context_size_before | INTEGER | bytes |
| context_size_after | INTEGER | bytes |
| tokens_removed | INTEGER | |
| snapshot_before | TEXT | last N messages JSON |
| snapshot_after | TEXT | post-compaction context JSON |
| timestamp | TEXT | ISO8601 |

### context_snapshots
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | autoincrement |
| session_id | TEXT FK | |
| context_size | INTEGER | bytes at snapshot time |
| trigger_event | TEXT | tool name or event type |
| delta_pct | REAL | % increase from previous |
| snapshot_json | TEXT | context content |
| timestamp | TEXT | ISO8601 |

## Prometheus Metrics

| Metric | Type | Labels | Description |
|---|---|---|---|
| opencode_interactions_total | Counter | session, tool | Total tool/model interactions |
| opencode_tokens_total | Counter | session, direction | Token consumption (input/output) |
| opencode_context_size_bytes | Gauge | session | Current context window size |
| opencode_compactions_total | Counter | session | Total compaction events |
| opencode_context_expansion_total | Counter | session, tool | Rapid expansion events (>threshold) |
| opencode_tool_duration_seconds | Histogram | session, tool | Tool execution latency |
| opencode_compaction_tokens_removed | Histogram | session | Tokens removed per compaction |

## Core Logic

### Compaction Snapshot
When `session.compacted` event arrives:
1. Query last N messages from `messages` as `snapshot_before`
2. After session status updates, capture new context as `snapshot_after`
3. Insert into `compactions`, compute `tokens_removed`

### Context Expansion Detection
On each `tool.execute.after` / `message.*.updated`:
1. Compare context size delta vs previous measurement
2. If delta > `expansion_threshold_pct` (default 50%), flag as expansion
3. Capture context snapshot → `context_snapshots` with triggering tool label
4. Increment `opencode_context_expansion_total` with tool label

## Configuration (config.yaml)
- `otel_data_dir`: path to OTLP JSON files
- `sqlite_path`: path to SQLite database file
- `expansion_threshold_pct`: 50
- `snapshot_message_count`: 20
- `poll_interval_seconds`: 5
- `metrics_port`: 9090

## Project Structure
```
agent-analyzer/
├── config.yaml
├── requirements.txt          # prometheus_client, pyyaml, watchdog
├── src/
│   ├── __init__.py
│   ├── main.py               # entry: start watchdog + HTTP server
│   ├── ingest.py             # OTLP JSON parser, SQLite writer
│   ├── models.py             # schema DDL, CRUD
│   ├── metrics.py            # Prometheus metric definitions + update
│   └── server.py             # HTTP /metrics, /health
├── tests/
│   ├── test_ingest.py
│   ├── test_models.py
│   └── test_metrics.py
└── grafana/
    └── dashboard.json        # Grafana dashboard template
```

## Grafana Dashboard Layout

- **Row 1 — Overview:** Stat panels (total interactions, tokens, compactions) + context size time series
- **Row 2 — Analysis:** Bar gauge (interactions by tool), heatmap (tool duration), time series (expansion events by tool)
- **Row 3 — Details:** Table (recent compactions with before/after sizes), table (recent expansion events with tool and delta%)

## Non-Goals
- Real-time streaming (poll-based is sufficient)
- Multi-user / team support (single developer focused)
- Custom alerting rules (Grafana handles that)
- Historical data migration / import
