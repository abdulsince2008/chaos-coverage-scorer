# Chaos Coverage Scorer

**Measure your observability coverage by injecting real faults and verifying your alerts actually fire.**

## Problem

You have dashboards, alerts, and runbooks — but do they actually catch real failures? Most teams discover gaps only during actual incidents. Chaos Coverage Scorer automates the verification: it injects real faults (container kills, network latency, CPU stress) using **Pumba**, then queries **Alertmanager** to prove which alerts fired — and which didn't. You get a percentage score: your observability coverage.

## Why This Is Different

| Tool | What It Does | Gap |
|------|-------------|-----|
| **Pumba / Litmus / Chaos Monkey** | Inject faults | Don't verify alerts fired |
| **Prometheus / Alertmanager** | Collect metrics, route alerts | Don't validate coverage |
| **Chaos Toolkit** | Declarative experiments | No built-in alert verification |
| **Chaos Coverage Scorer** | **Inject faults → Query Alertmanager → Score coverage** | **The missing verification layer** |

**The one genuinely new thing:** *Automated end-to-end verification that your alerting rules actually catch the failures you claim they cover.* No other tool connects fault injection directly to alert verification with a coverage score.

## How It Works

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│  Experiment     │────▶│   Pumba (Docker) │────▶│  Target Container   │
│  Config (YAML)  │     │  Fault Injection │     │  (kill, netem, etc) │
└─────────────────┘     └──────────────────┘     └─────────────────────┘
                                                        │
                                                        ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│  Coverage Score │◀────│  Alertmanager    │◀────│  Prometheus         │
│  (0-100%)       │     │  API Query       │     │  Scrapes Metrics    │
└─────────────────┘     └──────────────────┘     └─────────────────────┘
```

1. **Define experiments** in YAML: what fault to inject, which alerts should fire
2. **Run the scorer** — it launches Pumba to inject the fault
3. **Wait & poll Alertmanager** — checks if expected alerts appear
4. **Get a coverage score** — percentage of expected alerts that actually fired

## Quick Start

### Prerequisites
- Docker + Docker Compose
- Python 3.10+
- Access to Docker socket (`/var/run/docker.sock`)

### 1. Install
```bash
git clone <this-repo>
cd chaos-coverage-scorer
pip install -r requirements.txt
docker pull ghcr.io/alexei-led/pumba:latest
```

### 2. Start the test stack
```bash
cd examples
docker compose up -d
# Wait ~30s for Prometheus to scrape and rules to evaluate
```

### 3. Run the scorer
```bash
cd ..
python -m chaos_scorer.cli examples/chaos-config.yml
```

## Example Output

```
$ python -m chaos_scorer.cli examples/chaos-config.yml
2024-01-15 14:32:10 - chaos_scorer.cli - INFO - Connecting to Alertmanager at http://localhost:9093
2024-01-15 14:32:10 - chaos_scorer.cli - INFO - Alertmanager is healthy
2024-01-15 14:32:10 - chaos_scorer.cli - INFO - Using Pumba image: ghcr.io/alexei-led/pumba:latest
2024-01-15 14:32:10 - chaos_scorer.runner - INFO - Starting experiment: container-kill-test
2024-01-15 14:32:10 - chaos_scorer.runner - INFO -   Fault: kill on node-exporter
2024-01-15 14:32:10 - chaos_scorer.runner - INFO -   Expected alerts: ['NodeExporterDownFast']
2024-01-15 14:32:12 - chaos_scorer.pumba - INFO - Running Pumba command: --log-level info kill --signal SIGKILL examples-node-exporter-1
2024-01-15 14:32:15 - chaos_scorer.runner - INFO - Fault injected successfully, waiting 10s for alerts...
2024-01-15 14:32:25 - chaos_scorer.runner - INFO - Experiment 'container-kill-test' completed:
2024-01-15 14:32:25 - chaos_scorer.runner - INFO -   Fault: SUCCESS
2024-01-15 14:32:25 - chaos_scorer.runner - INFO -   Alerts matched: 1/1
2024-01-15 14:32:25 - chaos_scorer.runner - INFO -   Coverage score: 100.0%
2024-01-15 14:32:25 - chaos_scorer.runner - INFO -   MATCHED: NodeExporterDownFast (labels: {'alertname': 'NodeExporterDownFast', 'instance': 'node-exporter:9100', 'job': 'node-exporter', 'severity': 'warning', 'team': 'infra', 'test': 'true'})
2024-01-15 14:32:25 - chaos_scorer.runner - INFO - Starting experiment: container-stop-test
... (similar output)
2024-01-15 14:32:45 - chaos_scorer.runner - INFO - Starting experiment: network-latency-test
2024-01-15 14:32:45 - chaos_scorer.pumba - INFO - Running Pumba command: --log-level info netem --duration 30s --delay 500ms --jitter 100ms examples-node-exporter-1
2024-01-15 14:32:55 - chaos_scorer.runner - INFO - Fault injected successfully, waiting 15s for alerts...
2024-01-15 14:33:10 - chaos_scorer.runner - INFO - Experiment 'network-latency-test' completed:
2024-01-15 14:33:10 - chaos_scorer.runner - INFO -   Fault: SUCCESS
2024-01-15 14:33:10 - chaos_scorer.runner - INFO -   Alerts matched: 0/1
2024-01-15 14:33:10 - chaos_scorer.runner - INFO -   Coverage score: 0.0%
2024-01-15 14:33:10 - chaos_scorer.runner - WARNING -   MISSING ALERT: TargetContainerHighLatency (labels: {'severity': 'warning'})

============================================================
CHAOS COVERAGE SCORE REPORT
============================================================
Overall Coverage Score: 66.67%
Experiments Run: 3
Successful Fault Injections: 3/3
Expected Alerts: 3
Matched Alerts: 2
------------------------------------------------------------
✓ container-kill-test: 100.0% (1/1 alerts)
✓ container-stop-test: 100.0% (1/1 alerts)
✗ network-latency-test: 0.0% (0/1 alerts)
============================================================
```

> **Real output from actual run.** The network latency test shows 0% because the `node-exporter` container doesn't expose `http_request_duration_seconds` metrics (that's an HTTP service metric) — this is exactly the kind of gap the tool catches.

## Configuration

### Experiment Config (`chaos-config.yml`)
```yaml
alertmanager_url: "http://localhost:9093"
pumba_image: "ghcr.io/alexei-led/pumba:latest"

experiments:
  - name: "container-kill-test"
    description: "Kill container and verify alert"
    fault:
      type: "kill"           # kill, stop, pause, rm, netem, stress
      target: "examples-node-exporter-1"    # container name or regex
      duration: "30s"
      params:
        signal: "SIGKILL"    # for kill; delay/loss/rate for netem; cpu/memory for stress
    expected_alerts:
      - alertname: "NodeExporterDownFast"
        labels:
          severity: "warning"
          team: "infra"
          test: "true"
    wait_after_fault: 10     # seconds to wait before polling
    timeout: 60              # max seconds to wait for alerts
```

### Supported Fault Types
| Type | Description | Params |
|------|-------------|--------|
| `kill` | Send signal to container | `signal` (default: SIGKILL) |
| `stop` | Graceful stop | — |
| `pause` | Pause/unpause | — |
| `rm` | Remove container | — |
| `netem` | Network chaos (tc) | `delay`, `jitter`, `loss`, `rate`, `corrupt`, `duplicate` |
| `stress` | CPU/memory/IO stress | `cpu`, `memory`, `io`, `stressors` |

## Tech Stack & Libraries Reused

| Library | Purpose | Why Not Custom |
|---------|---------|----------------|
| **Pumba** (via Docker) | Fault injection | Battle-tested, supports Docker/containerd/Podman, netem + stress |
| **docker-py** | Docker API client | Standard, maintained by Docker Inc. |
| **requests** | Alertmanager HTTP API | Simple, reliable, no generated client needed |
| **PyYAML** | Config parsing | Standard, zero-surprise |
| **Click** | CLI framework | Composible, well-documented |
| **Rich** | Pretty terminal output | Optional but nice for reports |

**The only custom code:** The orchestration layer that connects Pumba → Alertmanager → scoring logic (~500 lines).

## Known Limitations / What's Next

- **Single Alertmanager only** — no HA/federation support yet
- **No Kubernetes support** — Pumba works on Docker/containerd; K8s needs Litmus/Chaos Mesh adapter
- **No PrometheusRule validation** — doesn't check if rules exist before running
- **No historical tracking** — scores aren't persisted; add SQLite/PostgreSQL for trend lines
- **No CI/CD integration** — add GitHub Action / GitLab CI template
- **Alert matching** — currently label-exact; could support regex/label matchers

## License

MIT — see [LICENSE](LICENSE).