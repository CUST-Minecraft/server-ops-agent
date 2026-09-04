# ServerOpsAgent

> [English](README.en.md) | 中文

一个面向单台 Linux 服务器的监测与受控运维 Agent。它的核心取舍不是“让 LLM 直接执行 shell”，而是：

```text
LLM 负责调查和提出判断
确定性代码负责工具边界、权限、审批、执行和验证
```

项目既是一个 Backend Agent 学习作品，也可以作为个人服务器和个人网站的运维原型使用。当前仍是单机、单目标机的学习版，不应直接当作生产级控制平面部署。

## 项目定位

ServerOpsAgent 通过 SSH 读取目标 Linux 服务器的指标和服务状态，在检测到异常后由 Agent 调查原因；涉及写操作时，经过权限策略和人工审批，再执行受限 Runbook，最后用确定性的后置条件验证修复结果。

```text
采集 -> 阈值检测/防抖 -> Incident
     -> LLM 调查 -> Runbook 选择
     -> 权限闸门 -> 人工审批（按策略）
     -> 受限修复 -> 断言式验证 -> 关单/告警
```

LLM 不是安全边界。Prompt 只是行为约束，真正的边界在 `PermissionEngine`、`ToolExecutor`、`ApprovalManager` 和 `Verifier`。

## 当前状态

截至 Day 16，核心代码、Web 门面、认证隔离和离线测试已经落地；Day 17 的故障注入评测和求职报告仍是后续工作。

| 阶段 | 状态 | 内容 |
|---|---|---|
| Day 1-3 | 已实现 | 配置、SSH/LLM 客户端、Tool、Registry、Agent Loop |
| Day 4-10 | 已实现 | 快照、检测、Incident、权限、审批、Runbook、Verifier、Runner、CLI、告警 |
| Day 11-12 | 已实现 | FastAPI Web 门面、MySQL 适配、SSH/LLM 重试、输出截断、注入防御基础 |
| Day 13-14 | 已实现 | 文件记忆、动态 System Prompt、上下文压缩、Web Chat、聊天落库 |
| Day 15 | 已实现 | bcrypt 登录、Token 生命周期、多用户聊天隔离、全业务 API 鉴权、实名审批归属 |
| Day 16 | 已实现 | pytest、FakeSSH、FakeLLM、SQLite 内存库、组件/集成测试 |
| Day 17 | 未实现 | 故障注入、指标评测、最终求职材料 |

当前离线回归结果：

```text
uv run pytest -q
57 passed, 8 subtests passed
```

前端构建产物 `static/` 不进入版本控制。部署或演示前必须由前端工程重新构建，不能假设干净 clone 自带构建后的页面。

## 最有价值的设计

### 1. LLM 判断与确定性执行分离

LLM 只能通过结构化工具调用影响系统，不能获得任意 shell 入口。所有工具调用进入唯一的 `ToolExecutor`，先过权限策略，再决定直接执行、需要审批或拒绝。

### 2. 执行成功不等于修复成功

`SSH exit_code=0` 只能说明命令执行结束。`Verifier` 会检查服务状态、端口等后置条件，只有断言通过才表示修复完成。

### 3. 审批绑定实际参数

`ApprovalRequest` 保存工具参数和 `args_hash`。审批时重新计算参数哈希，防止审批人看到的参数和实际执行的参数不一致。

### 4. 记忆与上下文分层

长期记忆保存在 `.memory/`，上下文压缩只处理当前会话。压缩故障曾导致 Agent 重复调用工具并撞上步数上限，后来通过压力门和工具结果保护修复并加入回归测试。

### 5. Web 安全基线

Web 已具备登录、Token 过期与注销、Token 哈希存储、聊天 `user_id` 归属、越权 403、全业务 API 鉴权、实名 `decided_by`、CSP 和基础安全响应头。

## 工具清单

工具分成只读诊断工具和写入修复工具。工具名、参数 schema、风险级别和执行 handler 都定义在 Python 代码中，并通过 `ToolRegistry` 暴露给 LLM。

### 只读诊断工具

这些工具不会主动修改目标服务器状态，默认走 `PermissionEngine` 的低风险放行路径。

| 工具 | 用途 | 实际远端命令 | 权限 |
|---|---|---|---|
| `get_cpu_status` | CPU 使用率和 1/5/15 分钟负载 | `top -bn1 \| grep 'Cpu(s)' ; uptime` | 普通用户 |
| `get_memory_usage` | 总内存、已用、可用和使用率 | `free -m` | 普通用户 |
| `get_disk_usage` | 指定绝对路径的磁盘使用率 | `df -h <path> \| tail -1` | 普通用户 |
| `get_service_status` | 查询 systemd 服务状态 | `systemctl is-active <service>` | 普通用户可读 |
| `read_service_logs` | 读取指定服务最近日志 | `journalctl -u <service> -n <1..200> --no-pager` | 普通用户；可能需要日志组 |
| `tcp_probe` | 探测目标机本机 TCP 端口 | `timeout 2 bash -c '</dev/tcp/127.0.0.1/<port>' && echo OPEN || echo CLOSED` | 普通用户 |

当前输入约束：

- 服务名只允许字母、数字、`.`、`_`、`-`。
- 磁盘路径必须是绝对路径，并拒绝 `..`。
- 日志行数限制在 1 到 200。
- TCP 端口限制在 1 到 65535。
- 工具输出有可配置的最大长度；但日志类 `ToolResult` 分支仍应在生产使用前复核脱敏和截断策略。

### 写入修复工具

当前内置写入工具只有：

| 工具 | 用途 | 实际命令 | 默认风险 |
|---|---|---|---|
| `restart_service` | 重启指定 systemd 服务 | `sudo -n systemctl restart <service>` | `medium`；关键服务动态升级为 `high` |

Runbook 当前只提供：

| Runbook | 动作 | 验证 |
|---|---|---|
| `nginx_restart` | 重启 nginx | nginx active + 80 端口可用 |
| `docker_restart` | 重启 Docker daemon | Docker active + 3306 端口可用 |

`docker_restart` 重启的是 Docker 服务，不是单独的 MySQL 容器。它可能影响目标机上的全部容器，这是有意保留的高影响操作，必须在实际使用前确认。

## 如何自定义工具

自定义工具必须通过 `Tool` 契约注册，不能在 Agent、Web 路由或 CLI 中直接调用 SSH。

### 工具契约

```python
from app.ssh.ssh_client import SSHClient
from app.tools.base import Tool


def build_custom_tools(ssh: SSHClient) -> list[Tool]:
    def nginx_health(_args: dict) -> dict:
        result = ssh.run("systemctl is-active nginx")
        if result["exit_code"] != 0:
            raise RuntimeError(result["stderr"] or "查询 nginx 状态失败")
        state = result["stdout"].strip() or "unknown"
        return {
            "service": "nginx",
            "state": state,
            "active": state == "active",
        }

    return [
        Tool(
            name="nginx_health",
            description="查询 nginx 是否处于 active 状态",
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            handler=nginx_health,
            risk_level="low",
        )
    ]
```

上面是一个完整的工具定义模式，但它不会自动注册。需要在 `app/runtime_deps.py` 的注册位置加入自定义 builder：

```python
for tool in (
    build_readonly_tools(ssh)
    + build_custom_tools(ssh)
    + build_remediation_tools(ssh)
):
    registry.register(tool)
```

### 自定义工具的安全要求

1. 只接受明确的参数类型和白名单值，不把用户或 LLM 输入直接拼接成任意 shell。
2. 只读工具显式使用 `risk_level="low"`；写工具必须显式声明 `medium` 或 `high`，不能依赖默认值。
3. `parameters` schema 必须和 handler 实际读取的字段一致。
4. 所有工具都通过 `ToolExecutor` 执行，不在 handler 外绕过权限和审计。
5. 写工具需要配套 Runbook、审批语义和后置条件验证。
6. 工具输出需要限长、脱敏，不能把密码、Token、Cookie、Authorization 头或整段敏感日志直接送入 LLM。
7. 每个工具都要有 FakeSSH 测试，至少断言参数校验、命令内容、失败结果和危险输入被拒绝。

### 自定义写工具的额外步骤

如果自定义工具会改变服务器状态，除了注册 Tool 之外，还必须：

```text
Tool(risk_level=medium/high)
    -> PermissionEngine 决策
    -> ApprovalRequest（standard/strict 模式）
    -> Runbook 白名单
    -> Verifier 后置条件
```

不要因为工具已经注册，就直接把它放进 `auto` 模式。`auto` 只适用于你明确评估过的中风险动作。

## 目标服务器权限模型

Agent 侧只保存 SSH 私钥，目标机只创建一个受限的 `opsagent` 账号。目标机不应给 Agent 全量 root、全量 sudo 或 Docker 管理权限。

### SSH 基础要求

- 目标机开放 TCP `22`，只允许 Agent 所在机器访问。
- `opsagent` 使用公钥认证，禁止依赖交互式密码。
- `opsagent` 使用可执行 `bash` 命令的登录 shell；当前工具依赖 `bash`、`timeout`、`top`、`free`、`df`、`tail`、`systemctl` 和 `journalctl`。
- 私钥只存在 Agent 侧，不能复制到目标机。
- 当前 SSH 实现仍使用 Paramiko `AutoAddPolicy()` 接受未知主机指纹。正式使用前应改为 pinned fingerprint 或受控 `known_hosts`，否则首次连接存在主机冒充风险。

### 只读命令

下列命令由当前只读工具执行，不需要 sudo：

```text
top -bn1 | grep 'Cpu(s)' ; uptime
free -m
systemctl is-active <validated service>
```

命令路径可能因发行版不同而变化。sudoers 中的绝对路径必须以目标机实际的 `command -v systemctl` 等结果为准；当前普通工具命令使用 PATH，不要仅凭文档中的路径判断。

### 日志读取权限

`journalctl` 能否读取完整系统日志取决于目标机配置。若确实需要读取系统级日志，可以：

- 使用更细的 per-service 日志访问策略；或
- 将 `opsagent` 加入 `systemd-journal` 组。

后者会扩大可读取的日志范围，日志可能含用户数据、Token 或请求头；个人网站环境应先评估敏感信息，再决定是否开放。

### 写命令白名单

当前 `restart_service` 执行的是：

```text
sudo -n systemctl restart nginx
sudo -n systemctl restart docker
```

与当前 Runbook 匹配的最小 sudoers 白名单是：

```text
opsagent ALL=(root) NOPASSWD: /usr/bin/systemctl restart nginx, /usr/bin/systemctl restart docker
```

写入 `/etc/sudoers.d/opsagent` 后，权限文件应为 `0440`，并使用 `visudo -c` 检查语法。目标机上真实路径如果不是 `/usr/bin/systemctl`，必须按实际路径修改。

### 明确禁止开放

不要授予：

```text
opsagent ALL=(root) NOPASSWD: ALL
opsagent ALL=(root) NOPASSWD: /usr/bin/systemctl
opsagent ALL=(root) NOPASSWD: /usr/bin/docker
usermod -aG docker opsagent
```

完整 Docker 权限近似 root 权限；全量 systemctl 也会允许停止网络、SSH、数据库等关键服务。新增自定义写工具时，只为具体命令增加精确白名单，不使用通配符扩大范围。

### 网络边界

- SSH 入站只允许 Agent 主机或管理网段。
- Web 应通过反向代理和 HTTPS 对外提供，不应直接把开发用 Uvicorn 端口暴露到公网。
- MySQL `3306` 只绑定内网、VPN 或 localhost，不对互联网开放。
- Web `8000` 只作为内部 upstream 或本机服务端口，不作为公共入口。

## Web 与认证边界

Web 端点分为：

```text
公开：登录入口、静态登录页面
受保护：状态、工单、审批、聊天、聊天历史、审批写操作
```

认证流程：

```text
用户名 + 密码
    -> bcrypt 校验
    -> 生成随机 Token
    -> 数据库只保存 SHA256(Token)
    -> 前端携带 Authorization: Bearer <token>
    -> get_current_user 校验存在、未过期、未注销
```

当前学习版还存在以下边界：

- `User.role` 已建模但尚未用于 RBAC；任何已登录用户都可能访问当前审批 API，不能把 Web 暴露给不可信用户群。
- 前端 Token 使用 `sessionStorage`，比 `localStorage` 更不持久，但同源 XSS 仍可读取；生产应考虑 HttpOnly Cookie、HTTPS 和更短的 Access Token。
- Web Chat 当前仍接收客户端提交的消息历史；正式使用前应让服务端以数据库历史为准，只接受当前用户的新消息。
- 登录限流、失败锁定、MFA、Token 轮换、完整越权审计尚未实现。

## 数据与运行边界

主要数据表：

```text
metric_snapshots       监控快照
incidents              异常工单
audit_logs             工具决策审计
approval_requests      审批单
remediation_records    修复和验证记录
chat_messages          按 user_id 隔离的聊天历史
users                  用户
auth_tokens            Token 哈希和生命周期
```

当前使用 SQLAlchemy，支持 SQLite 和 MySQL URL。`Base.metadata.create_all()` 只负责建缺失表，不负责升级已有表；长期使用前应补迁移方案、外键、索引和数据保留策略。

当前已知的工程限制：

- 自治 Runner 创建审批时的 Incident 关联仍需专项验收；在修复该关联前，不应宣称标准模式的审批恢复闭环已达到生产可靠性。
- 审批执行目前需要增加并发抢占/原子状态转换，避免两个审批请求同时执行同一动作。
- 监控快照、聊天、审计、Token 没有完整的清理和保留策略。
- 日志告警、SSH 生命周期、外部 LLM 数据脱敏仍需生产化加固。

## 测试与验证

测试完全可以离线运行：

- `FakeSSHClient` 替代目标服务器。
- `FakeLLM` 替代模型服务。
- StaticPool SQLite 内存库替代 MySQL。
- pytest 只收集 `serverAgentProgarm/tests/`，避免运行会连接真实 SSH 的 demo 文件。

```bash
cd serverAgentProgarm
uv sync
uv run pytest -q
uv run python -m compileall -q app tests
```

前端单独验证：

```bash
cd web
npm test
npm run build
```

## 仓库结构

```text
serverAgentProgarm/
├── app/
│   ├── agent/          Agent Loop、记忆、上下文压缩
│   ├── detect/         Detector、IncidentService
│   ├── llm/            OpenAI 兼容客户端
│   ├── monitor/        采集与巡检
│   ├── remediation/    Runbook、Verifier、修复服务
│   ├── runtime/        Runner、Investigator
│   ├── security/       权限、审批、认证、审计
│   ├── ssh/            SSH 通道
│   ├── storage/        SQLAlchemy 模型和数据库入口
│   ├── tools/          Tool、Registry、内置工具
│   └── web/            FastAPI 门面和静态页面托管
├── tests/              离线 pytest 测试和公共夹具
└── web/                Vue3 + Vite 前端工程
```

## 学习与设计文档

- 课程入口：[docs/README.md](docs/README.md)
- 架构演进：[docs/design/architecture.md](docs/design/architecture.md)
- API 设计：[docs/design/api-contract.md](docs/design/api-contract.md)
- ADR：[docs/design/adr/](docs/design/adr/)
- Day 16 测试过程：[docs/day16/test-process.md](docs/day16/test-process.md)
- Day 16 测试结果：[docs/day16/test-results.md](docs/day16/test-results.md)
- Day 15 前端安全报告：[docs/day15/frontend-security-remediation.md](docs/day15/frontend-security-remediation.md)

本 README 先说明项目能力、工具契约和权限边界；完整的部署、初始化、反向代理和日常操作手册另行编写。
