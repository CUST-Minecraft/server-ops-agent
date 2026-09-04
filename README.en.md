# ServerOpsAgent

> English | [中文](README.md)

ServerOpsAgent is a single-host Linux monitoring and controlled-operations Agent. Its central design rule is:

```text
The LLM investigates and proposes.
Deterministic code owns tools, permissions, approval, execution, and verification.
```

It is both a Backend Agent learning project and a prototype for personal servers and personal websites. It is currently a single-host learning-grade control plane, not a production-ready public service.

## What It Does

```text
collect -> threshold detection/debounce -> incident
        -> LLM investigation -> runbook selection
        -> policy gate -> approval when required
        -> constrained remediation -> postcondition verification
        -> resolve/alert
```

The LLM never receives an arbitrary shell endpoint. Tool calls go through `ToolExecutor`, policy decisions go through `PermissionEngine`, writes use `ApprovalManager`, and recovery is checked by `Verifier`.

## Current Status

Day 1 through Day 16 are implemented in the current project: monitoring, incidents, permissions, approvals, runbooks, verification, Runner, CLI, alerts, Web, authentication, multi-user chat ownership, and offline tests. Day 17 evaluation and final job-hunting material are not implemented yet.

Current offline regression:

```text
uv run pytest -q
57 passed, 8 subtests passed
```

## Built-in Tools

### Read-only diagnostics

| Tool | Purpose | Remote command | Permission |
|---|---|---|---|
| `get_cpu_status` | CPU and load averages | `top -bn1 \| grep 'Cpu(s)' ; uptime` | Normal user |
| `get_memory_usage` | Memory totals and usage | `free -m` | Normal user |
| `get_disk_usage` | Disk usage for an absolute path | `df -h <path> \| tail -1` | Normal user |
| `get_service_status` | systemd state | `systemctl is-active <service>` | Normal-user read access |
| `read_service_logs` | Recent service logs | `journalctl -u <service> -n <1..200> --no-pager` | Normal user; journal access may be needed |
| `tcp_probe` | Local TCP listener check | `timeout 2 bash -c '</dev/tcp/127.0.0.1/<port>' && echo OPEN || echo CLOSED` | Normal user |

### Remediation

| Tool | Purpose | Command | Default risk |
|---|---|---|---|
| `restart_service` | Restart a selected systemd service | `sudo -n systemctl restart <service>` | Medium; critical services are upgraded to high |

Current runbooks are `nginx_restart` and `docker_restart`. The latter restarts the Docker daemon, which can affect every container on the host; it does not only restart the MySQL container.

## Custom Tools

Add a tool through the `Tool` contract and register it in `app/runtime_deps.py`. Do not call SSH directly from Web, CLI, or Agent code.

```python
from app.ssh.ssh_client import SSHClient
from app.tools.base import Tool


def build_custom_tools(ssh: SSHClient) -> list[Tool]:
    def nginx_health(_args: dict) -> dict:
        result = ssh.run("systemctl is-active nginx")
        if result["exit_code"] != 0:
            raise RuntimeError(result["stderr"] or "nginx status check failed")
        state = result["stdout"].strip() or "unknown"
        return {"service": "nginx", "state": state, "active": state == "active"}

    return [Tool(
        name="nginx_health",
        description="Check whether nginx is active",
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=nginx_health,
        risk_level="low",
    )]
```

Register the builder beside the existing built-in builders. A write tool also needs an explicit risk level, a Runbook, approval semantics, a precise sudoers entry, a postcondition, and FakeSSH tests. Never add a general-purpose shell tool or give a future write tool the default low-risk classification.

## Target Host Permission Model

The Agent stores the SSH private key on the Agent host. The target host has a restricted `opsagent` account with a Bash login shell and public-key authentication.

### Required access

- Allow TCP `22` from the Agent host or management network only.
- Install the Agent public key in `opsagent`'s `authorized_keys`.
- Keep the target account out of the `docker` group.
- The read-only commands listed above need to be available in the target account's PATH.
- To read the complete system journal, use a per-service access policy where possible. Adding `opsagent` to `systemd-journal` grants broader log visibility and should be reviewed for sensitive data.

### Minimal write sudoers policy

The current remediation handler runs only:

```text
sudo -n systemctl restart nginx
sudo -n systemctl restart docker
```

The matching narrow policy is:

```text
opsagent ALL=(root) NOPASSWD: /usr/bin/systemctl restart nginx, /usr/bin/systemctl restart docker
```

Use the actual `systemctl` path on the target host, keep the sudoers file at mode `0440`, and validate it with `visudo -c`.

Do not grant:

```text
opsagent ALL=(root) NOPASSWD: ALL
opsagent ALL=(root) NOPASSWD: /usr/bin/systemctl
opsagent ALL=(root) NOPASSWD: /usr/bin/docker
usermod -aG docker opsagent
```

Full Docker access is effectively root access. Add one exact command only after reviewing its blast radius.

## Web Security Boundary

The login page and static assets are public entry points. Operational APIs require a valid Bearer Token. Tokens are bcrypt/opaque-token based at the application boundary, expire, can be revoked, and are stored as hashes in the database. Chat history is scoped by authenticated `user_id` and cross-user access is rejected.

This remains a learning-grade baseline:

- RBAC is modeled but not fully enforced; do not expose approval APIs to an untrusted user population.
- The frontend uses `sessionStorage`, which reduces persistence but does not protect against same-origin XSS. Production should use HTTPS and consider HttpOnly cookies or a protected refresh design.
- Chat history validation, approval/incident correlation, atomic approval claiming, SSH host-key pinning, rate limiting, retention, migrations, and complete audit hardening still need production work.

## Network Boundary

- Put the Web service behind a reverse proxy and HTTPS before public exposure.
- Do not expose Uvicorn port `8000` directly to the Internet.
- Bind MySQL port `3306` to localhost, a private network, or a VPN; never expose it publicly.
- Pin the target SSH host key before using the Agent on an untrusted network. The current SSH client still needs this production hardening.

## Offline Tests

The regression suite does not contact a real target host, LLM provider, or MySQL:

- `FakeSSHClient` replaces SSH.
- `FakeLLM` replaces the model service.
- StaticPool SQLite replaces MySQL.
- pytest only collects `serverAgentProgarm/tests/`.

```bash
cd serverAgentProgarm
uv sync
uv run pytest -q
```

## Repository Guide

```text
serverAgentProgarm/app/agent/          Loop, memory, context compaction
serverAgentProgarm/app/detect/         Detector and incident service
serverAgentProgarm/app/remediation/    Runbooks, verifier, remediation
serverAgentProgarm/app/runtime/        Runner and investigator
serverAgentProgarm/app/security/       Policy, approvals, auth, audit
serverAgentProgarm/app/tools/          Tool contract, registry, built-ins
serverAgentProgarm/app/web/            FastAPI facade and static hosting
serverAgentProgarm/tests/              Offline pytest suite and fixtures
serverAgentProgarm/web/                Vue 3 + Vite frontend
docs/                                  Course, architecture, ADRs, reports
```

Detailed deployment and daily-operation instructions are intentionally kept separate from this project overview and will be added later.
