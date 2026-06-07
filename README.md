# OpenCode Agent Metrics Dashboard

OpenCode 智能体上下文监控指标看板：通过 OpenTelemetry 采集数据，Python 中间层处理并暴露 Prometheus 指标，Grafana 可视化展示。

## 架构

```
OpenCode (telemetry 插件)
    │  OTLP JSON 文件
    ▼
Python 中间层
 ├── ingest.py   — 解析 OTLP，分类事件，写入 SQLite
 ├── models.py   — Schema DDL，CRUD 查询
 ├── metrics.py  — Prometheus Counter/Gauge/Histogram
 └── server.py   — HTTP /metrics (Prometheus 抓取), /health
    │  /metrics 端点
    ▼
Prometheus
    │
    ▼
Grafana (dashboard.json)
```

## 快速开始

### 1. 安装依赖

```bash
pip install prometheus_client pyyaml watchdog
```

### 2. 配置

编辑 `config.yaml`：

```yaml
otel_data_dir: "./data/otel"        # OTLP JSON 文件目录
sqlite_path: "./data/metrics.db"    # SQLite 数据库路径
expansion_threshold_pct: 50         # 上下文膨胀阈值 (%)
snapshot_message_count: 20          # 快照保留消息数
poll_interval_seconds: 5            # 文件扫描间隔
metrics_port: 9090                  # Prometheus 指标端口
```

### 3. 启动

```bash
python src/main.py
```

输出：
```
Watching ./data/otel for OTLP files, metrics on :9090
```

### 4. 配置 Prometheus

`prometheus.yml`：

```yaml
scrape_configs:
  - job_name: 'opencode-agent'
    scrape_interval: 15s
    static_configs:
      - targets: ['localhost:9090']
```

### 5. 导入 Grafana 看板

将 `grafana/dashboard.json` 导入 Grafana → Dashboards → Import。

## 指标说明

| 指标 | 类型 | 标签 | 描述 |
|---|---|---|---|
| `opencode_interactions_total` | Counter | session, tool | 交互总次数 |
| `opencode_tokens_total` | Counter | session, direction | Token 消耗量 |
| `opencode_context_size_bytes` | Gauge | session | 当前上下文大小 |
| `opencode_compactions_total` | Counter | session | Compaction 总次数 |
| `opencode_context_expansion_total` | Counter | session, tool | 上下文快速膨胀事件 |
| `opencode_tool_duration_seconds` | Histogram | session, tool | 工具调用耗时分布 |
| `opencode_compaction_tokens_removed` | Histogram | session | 每次压缩移除的 token 数 |

## Grafana 看板

- **Row 1 — Overview:** Stat 面板（交互总次数、Token 总量、Compaction 次数）+ 上下文大小趋势图
- **Row 2 — Analysis:** Bar gauge（各工具调用分布）、Heatmap（工具耗时）、折线图（膨胀事件按工具分类）
- **Row 3 — Details:** 表（最近 compaction 记录及压缩前后大小）、表（最近膨胀事件及触发工具和增长百分比）

## 项目结构

```
├── config.yaml           # 配置文件
├── requirements.txt      # Python 依赖
├── src/
│   ├── main.py           # 入口：启动 watchdog + HTTP server
│   ├── ingest.py         # OTLP JSON 解析 + 事件分类
│   ├── models.py         # SQLite schema + CRUD
│   ├── metrics.py        # Prometheus 指标定义 + 更新
│   └── server.py         # HTTP /metrics, /health
├── tests/
│   ├── conftest.py       # 共享 fixtures
│   ├── test_models.py    # 7 tests
│   ├── test_ingest.py    # 10 tests
│   ├── test_metrics.py   # 3 tests
│   └── test_integration.py # 1 集成测试
├── grafana/
│   └── dashboard.json    # Grafana 看板模板
└── docs/
    └── superpowers/
        ├── specs/        # 设计文档
        └── plans/        # 实现计划
```

## 运行测试

```bash
pytest tests/ -v
# 21 passed
```

## 数据流

1. OpenCode telemetry 插件输出 OTLP JSON 文件到 `otel_data_dir`
2. Python 中间层通过 watchdog + 轮询检测新文件
3. `ingest.py` 解析 JSON，分类事件（工具执行、消息、compaction、会话），写入 SQLite
4. 每次轮询后 `metrics.py` 从 SQLite 聚合数据并更新 Prometheus 指标
5. Prometheus 定时抓取 `/metrics` 端点
6. Grafana 使用预置看板模板展示可视化面板
