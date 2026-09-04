# ServerOpsAgent

> English | [中文](README.md)

A single-host Linux server monitoring and controlled-operations agent: collects metrics over SSH, detects anomalies, investigates root causes with an LLM, executes gated remediation after policy checks and human approval, and verifies recovery with deterministic postconditions.

```text
collect -> threshold detection (debounce/dedup) -> incident
       -> LLM investigation (tool loop) -> runbook selection
       -> policy gate -> approval (per mode) -> constrained fix
       -> postcondition assertions -> resolve/alert, fully audited
```

Design rule: the LLM investigates and proposes; it is never the security boundary. Tools, permissions, approvals, execution, and verification are owned by deterministic code.

## Features

- **Monitoring**: CPU / memory / disk / systemd service status, periodic snapshots into SQLite or MySQL (switchable by URL)
- **Anomaly detection**: thresholds + debounce streaks + incident dedup + auto-resolve on recovery
- **Agent investigation**: OpenAI-compatible function-calling loop; the model picks read-only tools, reads results, and iterates
- **Policy gates**: deny-list -> static risk -> dynamic escalation for critical services -> mode policy (standard / strict / auto)
- **Human-in-the-loop**: approval tickets bound to argument hashes with TTL; CLI and Web entries; approve-to-execute
- **Constrained remediation**: runbook whitelist (the model selects, never invents actions) + postcondition assertions — a successful command is not a successful fix
- **Web facade**: FastAPI JSON API + Vue3 frontend; login auth, token lifecycle, per-user chat isolation, named approval attribution
- **Context management**: four-layer compaction pipeline (trim / placeholder / summarize / reactive) + file-based cross-session memory
- **Offline tests**: full pytest regression with FakeSSH / FakeLLM / in-memory SQLite — no real server or model service required

## Quick Start

### Prerequisites

- Python 3.13+ with [uv](https://docs.astral.sh/uv/)
- A Linux target host (systemd) with SSH key login
- Any OpenAI-compatible LLM service (GLM / Kimi / DeepSeek / local vLLM all work)
- Node.js 18+ (only to build the web frontend)

### Install

```bash
git clone <repo-url>
cd server-agent/serverAgentProgarm
uv sync
cp .env.example .env   # fill in the config below
```

### Configuration

Key `.env` entries:

| Variable | Description |
|---|---|
| `SERVER_HOST` / `SERVER_PORT` / `SERVER_USER` / `KEY_PATH` | Target SSH connection; `KEY_PATH` must be absolute |
| `DB_URL` | `sqlite:///data/agent.db` or a MySQL URL |
| `API_KEY` / `BASE_URL` / `MODEL_ID` | OpenAI-compatible LLM service |
| `POLICY_MODE` | `standard` (default; writes need approval) / `strict` / `auto` |
| `WATCHED_SERVICES` | Comma-separated systemd services to watch |
| `THRESHOLD_*` | Detection thresholds and debounce counts (optional) |

See `.env.example` for the full list.

### Verify the Installation

```bash
uv run pytest -q                     # offline regression, no server needed
uv run python -m app.ssh.ssh_client  # verify SSH connectivity
```

### Run

```bash
# Autonomous loop (collect -> detect -> investigate -> approve -> fix -> verify)
uv run serveragent run

# CLI facade
uv run serveragent status        # latest snapshot + incidents + pending approvals
uv run serveragent approvals     # pending approval list
uv run serveragent approve 12    # approve and execute (actor is recorded)
uv run serveragent chat          # conversational investigation (login required)

# Web facade (build the frontend first)
cd web && npm install && npm run build && cd ..
uv run uvicorn app.web.app:app --port 8000
```

> Web login requires a bcrypt-hashed account in the `users` table. A user seeding script is not yet provided; accounts are currently created directly in the database (see the Web section).

## Built-in Tools

Tools are registered in a `ToolRegistry` that generates OpenAI function schemas. The LLM can only call registered tools.

### Read-only diagnostics (low risk, auto-allowed)

| Tool | Purpose | Remote command |
|---|---|---|
| `get_cpu_status` | CPU usage and load averages | `top -bn1 \| grep 'Cpu(s)' ; uptime` |
| `get_memory_usage` | Memory totals and usage | `free -m` |
| `get_disk_usage` | Disk usage for an absolute path | `df -h <path> \| tail -1` |
| `get_service_status` | systemd service state | `systemctl is-active <service>` |
| `read_service_logs` | Recent service logs (1-200 lines) | `journalctl -u <service> -n <n> --no-pager` |
| `tcp_probe` | Local TCP listener check | `timeout 2 bash -c '</dev/tcp/127.0.0.1/<port>'` |

### Remediation (medium risk, approval required by default)

| Tool | Purpose | Remote command |
|---|---|---|
| `restart_service` | Restart a systemd service | `sudo -n systemctl restart <service>` |

Built-in runbooks:

| Runbook | Action | Postcondition |
|---|---|---|
| `nginx_restart` | Restart nginx | nginx active + port 80 listening |
| `docker_restart` | Restart docker daemon (affects all containers) | docker active + port 3306 listening |

Input constraints: service names match a whitelist charset (alphanumerics `._-`); disk paths must be absolute and reject `..`; ports 1-65535; log lines 1-200.

## Custom Tools

Tools are the only SSH consumers. Adding a capability means defining a Tool and registering it — never call SSH from Agent, Web, or CLI code directly.

```python
# app/tools/custom.py
from app.ssh.ssh_client import SSHClient
from app.tools.base import Tool


def build_custom_tools(ssh: SSHClient) -> list[Tool]:
    def nginx_health(_args: dict) -> dict:
        r = ssh.run("systemctl is-active nginx")
        if r["exit_code"] != 0:
            raise RuntimeError(r["stderr"] or "check failed")
        state = r["stdout"].strip() or "unknown"
        return {"service": "nginx", "state": state, "active": state == "active"}

    return [Tool(
        name="nginx_health",
        description="Check whether nginx is active",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        handler=nginx_health,
        risk_level="low",
    )]
```

Register it in `app/runtime_deps.py`:

```python
for tool in build_readonly_tools(ssh) + build_custom_tools(ssh) + build_remediation_tools(ssh):
    registry.register(tool)
```

### Tool authoring rules

1. Validate arguments against a whitelist inside the handler; never concatenate input into arbitrary shell
2. Read-only tools use `risk_level="low"`; write tools declare `medium`/`high` explicitly — never rely on the default
3. Keep the `parameters` schema consistent with what the handler reads
4. Bound and redact output: passwords / tokens / cookies / Authorization headers must never reach the LLM context
5. Pair every tool with FakeSSH tests (argument validation, command content, failure paths, dangerous-input rejection)

### Checklist for write tools

Beyond registration, a write tool needs: a precise sudoers entry (below), a runbook definition (`app/remediation/runbooks.py`), postcondition assertions, and an explicit decision on approval semantics. `auto` mode auto-allows medium risk — validate new write tools under `standard` mode first.

## Target Host Permissions

The Agent host holds the private key. The target host only gets a restricted `opsagent` account (public-key auth + bash shell).

### Read-only commands (no sudo)

```text
top -bn1 | grep 'Cpu(s)' ; uptime
free -m
df -h <validated absolute path> | tail -1
systemctl is-active <validated service>
journalctl -u <validated service> -n <1..200> --no-pager
timeout 2 bash -c '</dev/tcp/127.0.0.1/<1..65535>' && echo OPEN || echo CLOSED
```

Reading the full system journal requires the `systemd-journal` group or a per-service policy; group membership widens log visibility (logs may contain sensitive data) — decide per deployment.

### Write-command sudoers whitelist

Built-in remediation runs exactly two commands; the minimal grant is:

```bash
echo 'opsagent ALL=(root) NOPASSWD: /usr/bin/systemctl restart nginx, /usr/bin/systemctl restart docker' | sudo tee /etc/sudoers.d/opsagent
sudo chmod 440 /etc/sudoers.d/opsagent
sudo visudo -c   # must print "parsed OK"
```

Adjust the path to the target host's actual `command -v systemctl` output.

### Never grant

```text
opsagent ALL=(root) NOPASSWD: ALL
opsagent ALL=(root) NOPASSWD: /usr/bin/systemctl
opsagent ALL=(root) NOPASSWD: /usr/bin/docker
usermod -aG docker opsagent
```

Full docker access is effectively root. Add exact commands one by one; no wildcards.

### Network boundaries

- SSH port 22 open only to the Agent host / management network
- Web served via reverse proxy + HTTPS; never expose the Uvicorn port directly
- MySQL port 3306 bound to localhost / private network / VPN only

## Web & Authentication

- Public endpoints: login and the static login page; every other business API requires `Authorization: Bearer <token>`
- Passwords stored as bcrypt hashes; the database stores only SHA256 hashes of tokens; tokens expire and can be revoked
- Chat history is scoped by `user_id`; cross-user access returns 403
- Approval actions record the logged-in username in `decided_by`

Current limitations (read before deploying): `User.role` is modeled but RBAC is not enforced — any logged-in user can access approval APIs, so expose the Web UI only to trusted users. Production use requires HTTPS, login rate limiting, HttpOnly cookie sessions, and role enforcement.

## Tests

Fully offline — no real server, LLM, or MySQL:

```bash
cd serverAgentProgarm
uv run pytest -q
```

- `FakeSSHClient`: returns canned outputs per command and records every call (assert "nothing executed after reject")
- `FakeLLM`: returns scripted tool_calls / final text (assert full protocol trajectories)
- StaticPool in-memory SQLite: fresh schema per test, zero cross-test pollution
- pytest collects `tests/` only; demo scripts with real SSH are never triggered

Frontend:

```bash
cd web && npm test && npm run build
```

## Repository Layout

```text
serverAgentProgarm/
├── app/
│   ├── agent/          loop, memory, context compaction
│   ├── detect/         detector, incident state machine
│   ├── llm/            OpenAI-compatible client
│   ├── monitor/        collector and scheduler
│   ├── remediation/    runbooks, assertion verifier
│   ├── runtime/        autonomous runner, investigator
│   ├── security/       policy, approvals, auth, audit
│   ├── ssh/            SSH channel
│   ├── storage/        SQLAlchemy models and DB entry
│   ├── tools/          Tool contract, registry, built-ins
│   └── web/            FastAPI facade
├── tests/              offline test suite
└── web/                Vue3 + Vite frontend
docs/                   architecture, ADRs, API contract, daily records
deploy/                 MySQL docker-compose
```

## Documentation

- Architecture and evolution: [docs/design/architecture.md](docs/design/architecture.md) (Chinese)
- API contract: [docs/design/api-contract.md](docs/design/api-contract.md) (Chinese)
- ADRs: [docs/design/adr/](docs/design/adr/)
- Test process and results: [docs/day16/test-process.md](docs/day16/test-process.md), [docs/day16/test-results.md](docs/day16/test-results.md)
- Frontend security audit: [docs/day15/frontend-security-remediation.md](docs/day15/frontend-security-remediation.md)

## Disclaimer

This project is built around the principle of wrapping LLM decisions in deterministic engineering. It is suitable for controlled personal-server operations, but it is not yet a production-grade control plane: SSH host-key pinning, atomic approval claiming, database migrations, enforced RBAC, and data-retention policies are still pending (see the docs). Complete those hardening steps before deploying on untrusted networks or multi-user environments.
