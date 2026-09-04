# ServerOpsAgent

单机 Linux 服务器的监测与受控运维 Agent：通过 SSH 采集指标、检测异常、由 LLM 调查根因，写操作经权限闸门与人工审批后执行受限修复，并以断言验证修复结果。

```text
采集 -> 阈值检测(防抖/去重) -> 开单 -> LLM 调查(工具循环)
     -> Runbook 选择 -> 权限闸门 -> 审批(按策略) -> 受限修复
     -> 后置条件断言 -> 关单/告警，全程审计留痕
```

设计原则：LLM 负责调查与判断，不作为安全边界；工具、权限、审批、执行、验证全部由确定性代码承担。

## 功能

- **监控采集**：CPU / 内存 / 磁盘 / systemd 服务状态，周期快照入库（SQLite / MySQL 可切换）
- **异常检测**：阈值 + 连击防抖 + 开单去重 + 恢复自动关单，避免告警风暴
- **Agent 调查**：OpenAI 兼容 function calling 循环，模型自主选择只读工具、回填结果、迭代推理
- **权限闸门**：黑名单拒绝 -> 静态风险 -> 关键服务动态升级 -> 模式策略（standard / strict / auto）
- **人工审批（HITL）**：审批单绑定参数哈希 + TTL，CLI / Web 双入口，批准即执行
- **受限修复**：Runbook 白名单（模型只选题不发明动作）+ 后置条件断言验证（执行成功 ≠ 修复成功）
- **Web 门面**：FastAPI JSON API + Vue3 前端；登录鉴权、Token 生命周期、多用户对话隔离、实名审批归属
- **上下文管理**：四层压缩管线（裁剪 / 占位 / 摘要 / 应急）+ 文件式跨会话记忆
- **离线测试**：pytest 全离线回归（FakeSSH / FakeLLM / SQLite 内存库），不依赖真实服务器与模型服务

## 快速开始

### 环境要求

- Python 3.13+ 与 [uv](https://docs.astral.sh/uv/)
- 目标 Linux 服务器（systemd），SSH 密钥登录
- 任一 OpenAI 兼容 LLM 服务（GLM / Kimi / DeepSeek / 本地 vLLM 均可）
- Node.js 18+（仅构建 Web 前端时需要）

### 安装

```bash
git clone <repo-url>
cd server-agent/serverAgentProgarm
uv sync
cp .env.example .env   # 填入下表配置
```

### 配置

`.env` 关键项：

| 变量 | 说明 |
|---|---|
| `SERVER_HOST` / `SERVER_PORT` / `SERVER_USER` / `KEY_PATH` | 目标机 SSH 连接信息；`KEY_PATH` 需绝对路径 |
| `DB_URL` | `sqlite:///data/agent.db` 或 MySQL URL |
| `API_KEY` / `BASE_URL` / `MODEL_ID` | OpenAI 兼容 LLM 服务 |
| `POLICY_MODE` | `standard`（默认，写操作需审批）/ `strict` / `auto` |
| `WATCHED_SERVICES` | 关注的 systemd 服务，逗号分隔 |
| `THRESHOLD_*` | 检测阈值与防抖次数，可选 |

完整清单见 `.env.example`。

### 验证安装

```bash
uv run pytest -q                    # 离线全回归，无需真实服务器
uv run python -m app.ssh.ssh_client # 验证 SSH 链路（输出结构化 dict 即通）
```

### 运行

```bash
# 自治闭环（采集->检测->调查->审批->修复->验证）
uv run serveragent run

# CLI 门面
uv run serveragent status        # 最新快照 + 工单 + 待审批摘要
uv run serveragent approvals     # 待审批清单
uv run serveragent approve 12    # 批准并执行（审计记录实名 actor）
uv run serveragent chat          # 对话式调查（需登录）

# Web 门面（先构建前端）
cd web && npm install && npm run build && cd ..
uv run uvicorn app.web.app:app --port 8000
```

> Web 登录需要 users 表中存在 bcrypt 哈希账号；用户初始化脚本尚未提供，当前通过数据库手工种入（见 Web 章节说明）。

## 内置工具

工具由 `ToolRegistry` 统一登记并生成 OpenAI function schema，LLM 只能调用注册过的工具。

### 只读诊断（低风险，自动放行）

| 工具 | 用途 | 远端命令 |
|---|---|---|
| `get_cpu_status` | CPU 使用率与 1/5/15 分钟负载 | `top -bn1 \| grep 'Cpu(s)' ; uptime` |
| `get_memory_usage` | 内存水位（总量/已用/可用/使用率） | `free -m` |
| `get_disk_usage` | 指定绝对路径的磁盘使用率 | `df -h <path> \| tail -1` |
| `get_service_status` | systemd 服务状态 | `systemctl is-active <service>` |
| `read_service_logs` | 服务最近日志（1-200 行） | `journalctl -u <service> -n <n> --no-pager` |
| `tcp_probe` | 目标机本机 TCP 端口探活 | `timeout 2 bash -c '</dev/tcp/127.0.0.1/<port>'` |

### 修复写入（medium 风险，默认需审批）

| 工具 | 用途 | 远端命令 |
|---|---|---|
| `restart_service` | 重启 systemd 服务 | `sudo -n systemctl restart <service>` |

内置 Runbook：

| Runbook | 动作 | 后置验证 |
|---|---|---|
| `nginx_restart` | 重启 nginx | nginx active + 80 端口监听 |
| `docker_restart` | 重启 docker daemon（影响全部容器） | docker active + 3306 端口监听 |

输入约束：服务名白名单字符集（字母数字`._-`）、磁盘路径必须绝对路径且拒绝 `..`、端口 1-65535、日志行数 1-200。

## 自定义工具

工具是唯一的 SSH 消费者。新增能力 = 定义 Tool + 注册，不在 Agent / Web / CLI 里直接调 SSH。

```python
# app/tools/custom.py
from app.ssh.ssh_client import SSHClient
from app.tools.base import Tool


def build_custom_tools(ssh: SSHClient) -> list[Tool]:
    def nginx_health(_args: dict) -> dict:
        r = ssh.run("systemctl is-active nginx")
        if r["exit_code"] != 0:
            raise RuntimeError(r["stderr"] or "查询失败")
        state = r["stdout"].strip() or "unknown"
        return {"service": "nginx", "state": state, "active": state == "active"}

    return [Tool(
        name="nginx_health",
        description="查询 nginx 是否处于 active 状态",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        handler=nginx_health,
        risk_level="low",
    )]
```

在 `app/runtime_deps.py` 注册：

```python
for tool in build_readonly_tools(ssh) + build_custom_tools(ssh) + build_remediation_tools(ssh):
    registry.register(tool)
```

### 工具编写要求

1. handler 内做参数白名单校验，不把输入拼接成任意 shell
2. 只读工具 `risk_level="low"`；写工具显式声明 `medium`/`high`，不依赖默认值
3. `parameters` schema 与 handler 实际读取的字段一致
4. 输出限长脱敏：密码 / Token / Cookie / Authorization 头不得进入 LLM 上下文
5. 每个工具配 FakeSSH 测试（参数校验、命令内容、失败路径、危险输入拒绝）

### 新增写工具清单

写工具除注册外还需要：精确 sudoers 白名单（见下）+ Runbook 定义（`app/remediation/runbooks.py`）+ 后置条件断言 + 审批语义确认。`auto` 模式会自动放行 medium 风险，新增写工具默认保持 `standard` 模式验证。

## 目标服务器权限

Agent 侧持有私钥，目标机只建受限账号 `opsagent`（公钥认证 + bash shell）。

### 只读命令（无需 sudo）

```text
top -bn1 | grep 'Cpu(s)' ; uptime
free -m
df -h <validated absolute path> | tail -1
systemctl is-active <validated service>
journalctl -u <validated service> -n <1..200> --no-pager
timeout 2 bash -c '</dev/tcp/127.0.0.1/<1..65535>' && echo OPEN || echo CLOSED
```

`journalctl` 完整系统日志需要 `systemd-journal` 组或 per-service 策略；加组会扩大日志可见范围（日志可能含敏感数据），按需取舍。

### 写命令 sudoers 白名单

内置修复只执行两条命令，最小授权：

```bash
echo 'opsagent ALL=(root) NOPASSWD: /usr/bin/systemctl restart nginx, /usr/bin/systemctl restart docker' | sudo tee /etc/sudoers.d/opsagent
sudo chmod 440 /etc/sudoers.d/opsagent
sudo visudo -c   # 必须输出 parsed OK
```

命令路径以目标机 `command -v systemctl` 实际结果为准。

### 禁止授予

```text
opsagent ALL=(root) NOPASSWD: ALL          # 全量 root
opsagent ALL=(root) NOPASSWD: /usr/bin/systemctl   # 可停止 sshd/network 等关键服务
opsagent ALL=(root) NOPASSWD: /usr/bin/docker       # docker 权限 ≈ root
usermod -aG docker opsagent
```

新增写工具时按具体命令逐条加白名单，不使用通配。

### 网络边界

- SSH 22 端口仅对 Agent 主机 / 管理网段开放
- Web 服务经反向代理 + HTTPS 对外提供，不直接暴露 Uvicorn 端口
- MySQL 3306 仅绑定 localhost / 内网 / VPN

## Web 与认证

- 公开端点：登录、静态登录页；其余业务 API 全部需要 `Authorization: Bearer <token>`
- 密码 bcrypt 哈希存储；数据库只存 Token 的 SHA256 哈希；Token 带过期时间、支持注销
- 聊天记录按 `user_id` 归属，跨用户访问返回 403
- 审批操作以登录用户名写入 `decided_by`

当前限制（部署前必读）：`User.role` 已建模但 RBAC 未强制执行，任何登录用户可访问审批 API——Web 只应暴露给可信用户群；生产使用需补 HTTPS、登录限流、HttpOnly Cookie 会话与角色控制。

## 测试

全离线，不连接真实服务器 / LLM / MySQL：

```bash
cd serverAgentProgarm
uv run pytest -q
```

- `FakeSSHClient`：按命令返回预置输出并记录全部调用（可断言"拒绝后什么都没执行"）
- `FakeLLM`：按剧本返回 tool_calls / 最终文本（可断言完整协议轨迹）
- StaticPool SQLite 内存库：每用例独立建表，零污染
- pytest 仅收集 `tests/`，不会触发 demo 脚本的真实 SSH

前端：

```bash
cd web && npm test && npm run build
```

## 目录结构

```text
serverAgentProgarm/
├── app/
│   ├── agent/          Loop、记忆、上下文压缩
│   ├── detect/         检测器、工单状态机
│   ├── llm/            OpenAI 兼容客户端
│   ├── monitor/        采集与巡检
│   ├── remediation/    Runbook、断言验证
│   ├── runtime/        自治 Runner、调查器
│   ├── security/       权限、审批、认证、审计
│   ├── ssh/            SSH 通道
│   ├── storage/        SQLAlchemy 模型与数据库入口
│   ├── tools/          Tool 契约、注册表、内置工具
│   └── web/            FastAPI 门面
├── tests/              离线测试套件
└── web/                Vue3 + Vite 前端
docs/                   架构、ADR、API 契约、每日记录
deploy/                 MySQL docker-compose
```

## 文档

- 架构与演进：[docs/design/architecture.md](docs/design/architecture.md)
- API 契约：[docs/design/api-contract.md](docs/design/api-contract.md)
- 架构决策记录（ADR）：[docs/design/adr/](docs/design/adr/)
- 测试过程与结果：[docs/day16/test-process.md](docs/day16/test-process.md)、[docs/day16/test-results.md](docs/day16/test-results.md)
- 前端安全审计报告：[docs/day15/frontend-security-remediation.md](docs/day15/frontend-security-remediation.md)

## 声明

本项目按"确定性工程包裹 LLM 决策"的思路构建，可用于个人服务器受控运维场景，但尚未达到生产级控制平面标准：SSH 主机指纹校验、审批并发抢占、数据库迁移、RBAC 强制执行、数据保留策略等仍在待办中（详见各文档）。在不可信网络或多人可访问环境中部署前，请先完成上述加固。
