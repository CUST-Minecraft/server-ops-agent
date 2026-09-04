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
cd server-ops-agent/serverAgentProgarm
uv sync
cp .env.example .env   # fill in the config below
```

### Configuration

Variables are loaded by the three settings models in `app/config.py`. The application fails configuration validation when a required value is missing; optional values use the defaults below.

| Variable | Required | Default | Description |
|---|---|---|---|
| `SERVER_HOST` | Yes | None | Target Linux server address |
| `SERVER_PORT` | No | `22` | SSH port, 1-65535 |
| `SERVER_USER` | Yes | None | SSH user; a restricted `opsagent` account is recommended |
| `KEY_PATH` | Yes | None | SSH private-key path; use an absolute path |
| `DB_URL` | Yes | None | Database URL, such as `sqlite:///data/agent.db` or a MySQL URL |
| `LOG_LEVEL` | Yes | None | Log level, such as `INFO` or `WARNING` |
| `API_KEY` | Yes | None | OpenAI-compatible LLM API key |
| `BASE_URL` | Yes | None | OpenAI-compatible LLM endpoint, such as `https://api.example.com/v1` |
| `MODEL_ID` | Yes | None | LLM model identifier |
| `MONITOR_INTERVAL` | No | `30` | Autonomous polling interval in seconds |
| `WATCHED_SERVICES` | No | `ssh,docker` | Comma-separated systemd services to watch |
| `POLICY_MODE` | No | `standard` | `standard`/`strict` require approval for writes; `auto` allows medium risk automatically, while high risk still requires approval |
| `APPROVAL_TTL_MINUTES` | No | `60` | Approval-request lifetime in minutes |
| `INVESTIGATE_MAX_RETRIES` | No | `2` | Maximum retries after a failed investigation or no runbook recommendation |
| `ALERT_WEBHOOK_URL` | No | Empty | Optional alert webhook; console alerts remain enabled without it |
| `MAX_OUTPUT_CHARS` | No | `8000` | Maximum tool-result characters sent to the LLM |
| `MEMORY_CONSOLIDATE_THRESHOLD` | No | `10` | Number of memory files that triggers consolidation |
| `COMPACT_TOKEN_THRESHOLD` | No | `24000` | Estimated token count that triggers context compaction |
| `THRESHOLD_CPU_PCT` | No | `85` | CPU alert threshold, percent |
| `THRESHOLD_MEM_PCT` | No | `85` | Memory alert threshold, percent |
| `THRESHOLD_DISK_PCT` | No | `80` | Disk alert threshold, percent |
| `THRESHOLD_SUSTAIN` | No | `3` | Consecutive CPU/memory/disk threshold breaches |
| `THRESHOLD_SERVICE_SUSTAIN` | No | `2` | Consecutive abnormal systemd-service readings |

Copy `.env.example` and replace the required values. The `THRESHOLD_*` variables are loaded by `ThresholdSettings` through its `THRESHOLD_` environment prefix.

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

> On startup, the Web app calls `init_db()` from `app/storage/db.py` and creates missing tables, including `users`; it does not create the first account. There is currently no user-seeding command, so create one bcrypt-hashed account before the first login.

### Database and First Web User

`app/storage/db.py` is the database schema initialization entry point:

```bash
cd serverAgentProgarm
uv run python -m app.storage.db
```

This calls `Base.metadata.create_all(engine)` and creates missing tables such as `users`, `auth_tokens`, incidents, and audit logs. It does not delete existing data or create a default user. The Web app runs the same `init_db()` during startup, so you normally do not need to run it separately.

To create the first user, generate a bcrypt hash first:

```bash
uv run python -c "from app.security.auth import hash_password; print(hash_password('replace-with-a-strong-password'))"
```

Then insert the account into the database configured by `DB_URL` (replace `<bcrypt-hash>` with the complete output):

```sql
INSERT INTO users (username, password_hash, role, created_at)
VALUES ('admin', '<bcrypt-hash>', 'admin', CURRENT_TIMESTAMP);
```

Do not put the plaintext password in the repository, `.env`, or shell history. In production, generate and enter the hash through a password manager or an interactive process.

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

### Built-in runbooks

| Runbook | Action | Postcondition |
|---|---|---|
| `nginx_restart` | Restart nginx | nginx active + port 80 listening |
| `docker_restart` | Restart docker daemon (affects all containers) | docker active + port 3306 listening |

Input constraints: service names match a whitelist charset (alphanumerics `._-`); disk paths must be absolute and reject `..`; ports 1-65535; log lines 1-200.

### How Runbooks Work

A runbook is not a shell command that the LLM can invent. It is an allowlisted remediation definition:

1. The investigator gives the LLM each runbook's `name` and `trigger`; the final answer may contain an exact registered name or `null`.
2. The Runner looks up that name in `RUNBOOKS`. A name outside the allowlist is never executed.
3. `plan` invokes exactly one registered Tool with a fixed argument dictionary. The LLM cannot rewrite those arguments.
4. After the Tool succeeds, the Verifier executes every read-only check in `postcondition.checks`. All `expect` key/value pairs must match for the result to be `verified`.
5. A medium/high-risk Tool still goes through the policy and approval flow; a runbook never bypasses the permission gate.

`trigger` is guidance for the LLM, not a security check. `description` and `risk_note` are runbook metadata. In the current implementation, `plan` does not support `${...}` placeholders, runtime parameters, or a multi-step plan list: one runbook means one Tool call plus multiple postcondition checks.

### Customize a Runbook: Reuse an Existing Tool

If you only need a restart runbook for another systemd service, you do not need to write a new Tool. Edit `serverAgentProgarm/app/remediation/runbooks.py` and add a new `Runbook` to `RUNBOOKS`:

```python
Runbook(
    name="api_restart",  # unique; the LLM must return this exact string
    description="Restart the api service",
    trigger="Use when api is inactive/failed or port 8080 is unreachable",
    plan={
        "tool": "restart_service",  # must be a registered Tool
        "args": {"service": "api"},
    },
    postcondition={
        "checks": [
            {
                "tool": "get_service_status",  # registered read-only Tool
                "args": {"service": "api"},
                "expect": {"active": True},  # keys from the Tool's data
            },
            {
                "tool": "tcp_probe",
                "args": {"port": 8080},
                "expect": {"port_open": True},
            },
        ]
    },
    risk_note="api is briefly unavailable during restart",
),
```

Steps:

1. Add the object to the `RUNBOOKS` list and keep `name` unique.
2. Confirm that `api.service` exists on the target host and set the actual listening port in `tcp_probe`; remove checks you do not need.
3. If `api` is not allowed by the target host's sudoers whitelist, add one exact command as described in the permissions section.
4. Test on a non-production host in `auto` mode:

   ```bash
   cd serverAgentProgarm
   uv run python demo/run_runbook.py api_restart
   ```

5. Keep `POLICY_MODE=standard` in production. Run `uv run serveragent approvals` to inspect the request and `uv run serveragent approve <approval-id>` to approve it; the autonomous Runner performs the postcondition checks on its next tick.

The `expect` object must use keys returned in the Tool's `data`. For example, `get_service_status` returns `active`, while `tcp_probe` returns `port_open`; an unknown key makes verification fail.

## Custom Tools

Tools are the only SSH consumers. Adding a capability means defining a Tool and registering it — never call SSH from Agent, Web, or CLI code directly.

```python
# create app/tools/custom.py
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

Register it at the shared assembly point, `app/runtime_deps.py`. Otherwise a runbook's `plan.tool` or a postcondition check cannot find the Tool:

```python
from app.tools.custom import build_custom_tools

for tool in (
    build_readonly_tools(ssh)
    + build_custom_tools(ssh)
    + build_remediation_tools(ssh)
):
    registry.register(tool)
```

### Tool authoring rules

1. Validate arguments against a whitelist inside the handler; never concatenate input into arbitrary shell
2. Read-only tools use `risk_level="low"`; write tools declare `medium`/`high` explicitly — never rely on the default
3. Keep the `parameters` schema consistent with what the handler reads
4. Bound and redact output: passwords / tokens / cookies / Authorization headers must never reach the LLM context
5. Pair every tool with FakeSSH tests (argument validation, command content, failure paths, dangerous-input rejection)

### Checklist for write tools

If the action cannot be implemented by an existing Tool, add it in this order:

1. Define it in `app/tools/remediation.py` or a custom module, validate arguments strictly, and declare `risk_level="medium"` or `"high"` explicitly.
2. Register it in `app/runtime_deps.py`; the runbook's `plan.tool` must exactly equal `Tool.name`.
3. Allow only the exact command in target-host sudoers; never use `ALL` or a wildcard.
4. Add a Runbook in `app/remediation/runbooks.py` and use read-only Tools for its postconditions.
5. Add FakeSSH tests for argument validation, the exact SSH command, failure paths, and dangerous input.

`auto` only auto-allows medium risk; high risk (for example, critical services) still requires approval. Validate new write Tools under `standard` before enabling automation.

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
deploy/                 MySQL docker-compose
```

## Documentation

- Usage, configuration, Runbooks, and permission boundaries: this README
- Chinese version: [README.md](README.md)
- Python subproject notes: [serverAgentProgarm/README.md](serverAgentProgarm/README.md)
- `docs/` contains local learning and design notes. It is ignored by `.gitignore` and is not published to GitHub.

## Disclaimer

This project is built around the principle of wrapping LLM decisions in deterministic engineering. It is suitable for controlled personal-server operations, but it is not yet a production-grade control plane: SSH host-key pinning, atomic approval claiming, database migrations, enforced RBAC, and data-retention policies are still pending. Complete those hardening steps before deploying on untrusted networks or multi-user environments.
