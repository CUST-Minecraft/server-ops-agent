# ServerOpsAgent -- Autonomous Server Monitoring & Ops Agent

> English | [中文](README.md)

> A single-host autonomous ops agent that wraps LLM decision-making in deterministic engineering:
> monitors a Linux server over SSH, investigates anomalies, applies gated fixes, verifies closed-loop, and logs everything.

## In One Sentence

**The LLM does exactly one thing -- investigate and propose, like an on-call engineer.**
Low-risk actions run autonomously; high-risk ones require human approval. Everything is audited, and every fix is re-verified.

## Current Progress

> This project grows day by day along a 15-day curriculum, currently at **Day 3**. "Done" below is what actually runs today; "Planned" is the curriculum target.

### Done (Day 1 - Day 3)

| Day | Deliverables | What it can do |
|---|---|---|
| D1 | `config.py` / `SSHClient` / `LLMClient` / `setup_logging()` | Config injected from `.env`; SSH public-key login to target host; OpenAI-compatible API wired up; unified logging |
| D2 | `Tool` contract / 5 read-only tools / `ToolRegistry` | Five read-only tools (CPU / memory / disk / systemd status / journalctl); registry generates OpenAI function schemas |
| D3 | `ToolResult` three-state / `ToolExecutor` / Agent Loop / `agent_chat.py` | Conversational agent that picks tools, feeds back results, and iterates; executor never raises; max_steps guardrail |

Runnable today: `uv run python demo/agent_chat.py` -- ask it "how are the server resources?" and it will call `get_cpu_status` / `get_memory_usage` / `get_disk_usage` and answer from real data.

### Planned (Day 4 - Day 15)

```text
D4  Polling + persistence   D5  Detection + incidents   D6  Permission gates
D7  Human approval (HITL)   D8  Gated fixes + asserts   D9  Autonomous loop
D10 CLI + alerts (MVP)      D11 Web + MySQL             D12 Injection/failure hardening
D13 Offline tests           D14 Chaos-injected eval     D15 Job-hunt materials
```

Full 15-day roadmap: [docs/README.md](docs/README.md) (in Chinese).

## How to Learn from This Repo

This is a **job-hunting-oriented learning project** with a complete 15-day curriculum (each day ships a tutorial README, a task list, and study notes):

```text
docs/
├── README.md          Course entry (usage, 15-day roadmap, 10-day fast track)
├── day01/ ... day15/  Daily trio (README + task + notes)
├── research/          External research notes (learn-claude-code / Hello-Agents / HolmesGPT)
└── design/            Architecture principles, evolution, 5 ADRs
```

**Start here**: [docs/README.md](docs/README.md) -> [Day 1](docs/day01/README.md)

## Key Features (End State)

> The target shape after all 15 days; not all of it is built yet (see "Current Progress").

- SSH monitoring of a single Linux host: CPU / memory / disk / systemd services / logs / TCP probes
- Anomaly detection (thresholds + debounce streaks + incident dedup) -> six-state incident machine
- Agent investigation loop (ReAct / OpenAI-compatible function calling): three-state tool results, iteration guardrails, output truncation
- Four-layer permission gates: deny-list -> static risk -> per-parameter dynamic escalation -> mode policy (standard/strict/auto)
- Human-in-the-loop: approval tickets (param-hash binding + TTL + append-only audit), CLI / Web entries
- Gated remediation: runbook whitelist (the LLM picks a playbook, never invents actions) + post-condition assertions for closed-loop verification
- 30+ pytest offline regression (FakeSSH / FakeLLM); chaos-injected evaluation (detection rate / localization accuracy / fix success rate / MTTR)

## Tech Stack

Python 3.13 / hand-written agent loop (no heavyweight framework, see [ADR-0005](docs/design/adr/0005-no-framework.md)) / OpenAI-compatible API (`openai` SDK; switchable to GLM, Kimi, DeepSeek, etc.) / paramiko / SQLAlchemy 2 (SQLite -> MySQL in one line) / FastAPI + Jinja2 / typer / pytest

## Quick Start

```bash
# Prereqs: a Linux VM + SSH key login + an LLM API key
#          (full setup steps: serverAgentProgarm/README.md, in Chinese)
cd serverAgentProgarm
uv sync
cp .env.example .env       # fill in config (server / SSH key / LLM key / DB_URL / LOG_LEVEL)
uv run python demo/agent_chat.py    # the conversational agent, runnable today
```

## Target Architecture

```text
CLI / Web ──> ApprovalManager ──> ToolExecutor ──> Permission Engine (4 layers) ──> Tools ──SSH──> Linux
                  ▲                    │                                                 │
Runner loop ──────┤                    └── AuditLog                                     ▼
  collect->detect->incident FSM->LLM investigate->runbook match->fix->assert->close  MySQL (5 tables, full audit trail)
                                        └── Alerter ──> human
```

> Only the `Tools ─SSH─> Linux` path and the agent loop exist today; the rest grows with the curriculum.

Five architecture principles: `Agent != Tool`, `Tool != SSH`, `Permission != execution`, `Monitoring != LLM`, `LLM != security boundary` (expanded in [docs/design/README.md](docs/design/README.md), in Chinese)

## Learning-Project Disclaimer

This is a **job-hunting-oriented learning project**. It borrows ideas from learn-claude-code, Hello-Agents, and HolmesGPT; every design decision (what was researched -> what was considered -> what was rejected -> what was chosen -> why) is documented in [docs/research/](docs/research/) and [docs/design/adr/](docs/design/adr/) (in Chinese).
