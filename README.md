# ServerOpsAgent

单机 Linux 服务器的监测与受控运维 Agent：通过 SSH 采集指标、检测异常、由 LLM 调查根因，写操作受权限策略约束、按风险与模式经过人工审批后执行受限修复，并以断言验证修复结果。

```text
采集 -> 阈值检测(防抖/去重) -> 开单 -> LLM 调查(工具循环)
     -> Runbook 选择 -> 权限闸门 -> 审批(按策略) -> 受限修复
     -> 后置条件断言 -> 关单/告警，全程审计留痕
```

设计原则：LLM 负责调查与判断，不作为安全边界；工具、权限、审批、执行、验证全部由确定性代码承担。

## 功能

- **监控采集**：CPU / 内存 / 磁盘 / systemd 服务状态，周期快照入库（SQLite / MySQL 可切换）
- **异常检测**：阈值 + 连击防抖 + 开单去重 + 恢复自动关单，避免告警风暴
- **Agent 调查**：OpenAI 兼容 function calling 循环，模型选择已注册工具、由代码校验执行、回填结果并继续推理
- **MCP 扩展**：可选的本地 stdio 只读调查工具，白名单、参数范围和接口契约检查，复用原 Executor 与审计
- **历史案例 RAG**：已验证修复证据生成案例，本地关键词与向量混合检索，附来源并支持关键词降级
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
git clone https://github.com/CUST-Minecraft/server-ops-agent.git
cd server-ops-agent/serverAgentProgarm
uv sync --locked
mkdir -p data
cp .env.example .env   # 填入下表配置
```

### 配置

`.env` 中的变量由 `app/config.py` 的三个配置模型读取。相关配置模型实例化时校验必填项，缺失会直接报错；选填项省略时使用默认值。

| 变量 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `SERVER_HOST` | 是 | 无 | 目标 Linux 服务器地址 |
| `SERVER_PORT` | 否 | `22` | SSH 端口，范围 1-65535 |
| `SERVER_USER` | 是 | 无 | 目标机 SSH 用户，建议使用受限的 `opsagent` |
| `KEY_PATH` | 是 | 无 | SSH 私钥路径，建议填写绝对路径 |
| `DB_URL` | 是 | 无 | 数据库连接，例如 `sqlite:///data/agent.db` 或 MySQL URL |
| `LOG_LEVEL` | 是 | 无 | 日志级别，例如 `INFO`、`WARNING` |
| `API_KEY` | 调查/对话时 | 无 | OpenAI 兼容 LLM 服务 API Key |
| `BASE_URL` | 调查/对话时 | 无 | OpenAI 兼容 LLM 服务地址，例如 `https://api.example.com/v1` |
| `MODEL_ID` | 调查/对话时 | 无 | LLM 模型名称 |
| `MCP_ENABLED` | 否 | `false` | 启用经审查的本地 MCP 调查工具 |
| `MCP_CONFIG_PATH` | 否 | `mcp.json` | 相对 Python 子项目根目录的配置路径，或绝对路径 |
| `MONITOR_INTERVAL` | 否 | `30` | 自治巡检间隔，单位秒 |
| `WATCHED_SERVICES` | 否 | `ssh,docker` | 关注的 systemd 服务，逗号分隔 |
| `POLICY_MODE` | 否 | `standard` | `standard`/`strict`：写操作需审批；`auto`：medium 风险自动放行，high 风险仍需审批 |
| `APPROVAL_TTL_MINUTES` | 否 | `60` | 审批单有效期，单位分钟 |
| `INVESTIGATE_MAX_RETRIES` | 否 | `2` | 调查失败或无预案时的最大重试次数 |
| `ALERT_WEBHOOK_URL` | 否 | 空 | 可选告警 Webhook；不填写时只输出控制台告警 |
| `MAX_OUTPUT_CHARS` | 否 | `8000` | 工具结果传给 LLM 前的最大字符数 |
| `MEMORY_CONSOLIDATE_THRESHOLD` | 否 | `10` | 记忆文件达到该数量后触发整理 |
| `COMPACT_TOKEN_THRESHOLD` | 否 | `24000` | 对话估算 token 超过该值时触发上下文压缩 |
| `THRESHOLD_CPU_PCT` | 否 | `85` | CPU 告警阈值，百分比 |
| `THRESHOLD_MEM_PCT` | 否 | `85` | 内存告警阈值，百分比 |
| `THRESHOLD_DISK_PCT` | 否 | `80` | 磁盘告警阈值，百分比 |
| `THRESHOLD_SUSTAIN` | 否 | `3` | CPU/内存/磁盘连续超阈值次数 |
| `THRESHOLD_SERVICE_SUSTAIN` | 否 | `2` | systemd 服务连续异常次数 |

先复制 `.env.example` 并修改所需必填项。Windows PowerShell 可用 `New-Item -ItemType Directory -Force data` 创建 SQLite 数据目录。MCP 与 RAG 的启用步骤及额外变量见下文；其中 `THRESHOLD_*` 变量由 `ThresholdSettings` 的 `THRESHOLD_` 前缀读取。

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
uv run serveragent approve 12    # 批准并执行（CLI 默认 actor 为 operator）
uv run serveragent chat          # 对话式调查（需登录）

# Web 门面（先构建前端）
cd web && npm ci && npm run build && cd ..
uv run uvicorn app.web.app:app --port 8000
```

前端未构建时，Web 模块仅提供 API，页面路径返回 404；构建后重启 Web 进程即可挂载页面。

> Web 启动时会调用 `app/storage/db.py` 的 `init_db()`，自动创建缺失的数据表（包括 `users`）；但它只建表，不会自动创建首个账号。当前项目尚未提供用户 seed 命令，首次登录前仍需单独创建一个 bcrypt 哈希账号。

### 数据库与首个 Web 用户

`app/storage/db.py` 是数据库初始化入口：

```bash
cd serverAgentProgarm
uv run python -m app.storage.db
```

这条命令会执行 `Base.metadata.create_all(engine)`，创建 `users`、`auth_tokens`、工单和审计等缺失表；不会删除已有数据，也不会创建默认用户。Web 应用启动时会自动执行同一个 `init_db()`，通常不必重复运行。

创建首个用户时，先生成 bcrypt 哈希：

```bash
uv run python -c "from getpass import getpass; from app.security.auth import hash_password; print(hash_password(getpass('Password: ')))"
```

再在当前 `DB_URL` 指向的数据库中插入账号（把 `<bcrypt-hash>` 替换为上一步完整输出）：

```sql
INSERT INTO users (username, password_hash, role, created_at)
VALUES ('admin', '<bcrypt-hash>', 'admin', CURRENT_TIMESTAMP);
```

已有数据库升级注意：本次新增了修复上下文、案例表及工单调查字段。`create_all` 只创建缺失表，不会为已有表补列或修改约束；仓库尚未提供自动迁移。升级前先备份并按模型差异完成数据库迁移，新建空库则直接初始化。

密码明文不要写入仓库、`.env` 或命令历史；生产环境应通过密码管理工具或交互式方式生成和录入哈希。

## MCP 工具扩展

基础监控继续由内置代码采集 CPU、内存、磁盘和服务状态。MCP 用于接入不同环境的调查工具，例如数据库连接数查询；新增工具不会自动变成周期监控项或修复预案。

当前支持本地 `stdio`、经审查的只读工具，默认 `MCP_ENABLED=false`。通信使用锁文件中的 Python MCP SDK 2.3.0；本版本没有实现远程 HTTP MCP、MCP 写工具审批或连接池。

```text
本地配置 -> tools/list -> 白名单 / Schema 契约核对 -> 适配为项目 Tool
模型提出调用 -> ToolExecutor / Policy / 审计 -> MCP Client -> MCP Server
           <- ToolResult <- 结果校验 / 脱敏 / 限长
原 Agent Loop 按 tool_call_id 回填观察 -> 模型继续分析
```

### 先运行完整离线演示

在 `serverAgentProgarm` 目录执行：

```bash
uv run python -m demo.mcp_smoke
```

演示实际启动 MCP 子进程，经过原 Agent Loop、Executor、策略检查、结果回填和审计。模型使用脚本模拟，数据库连接数是合成数据，不会请求真实 LLM、SSH 或业务数据库；因此它验证的是调用链路。

### 配置并启用

1. 复制 `mcp.example.json` 为 `mcp.json`。后者包含本机配置，已被 Git 忽略。
2. 示例中的 `command` 和 `cwd` 是占位路径，必须改成当前机器上存在的绝对路径。在 Python 子项目目录执行以下命令，获取可直接复制的 JSON 字段（兼容 Windows 路径转义）：

   ```bash
   uv run python -c "import json,sys; from pathlib import Path; print(json.dumps(dict(command=sys.executable,cwd=str(Path.cwd())),ensure_ascii=False,indent=2))"
   ```

   `args` 保留为 `["demo/mcp_dbdiag_server.py"]`，由配置的 `cwd` 解析。示例只允许查询 `shop`、`empty` 两个教学目标。
3. 显式检查工具发现和准入。此命令会启动配置中的本地程序，但不会调用数据库查询工具，也不需要 SSH / LLM 配置：

   ```bash
   uv run serveragent mcp tools --config mcp.json
   ```

4. 在本地 `.env` 中设置 `MCP_ENABLED=true`、`MCP_CONFIG_PATH=mcp.json`，重新启动 CLI chat、Web 或自治 Runner。实际调查仍需要正常的 SSH / LLM 等基础配置。审批列表、批准和拒绝入口不会启动 MCP Server。

### 接入自己的 Server

- 在独立 MCP Server 中实现真实查询函数；将本地配置的 `command / args / cwd` 指向经过审查的程序。模型无权指定启动命令。
- 为工具设置远端名称、本地唯一别名、由本地维护的说明、显式 `risk_level="low"`，以及 `allowed_arguments` 参数取值白名单。未配置资源范围的字段仍只受 Schema 约束，实际数据源也应使用受限账号。
- 审查输入、输出 Schema 后，记录 `expected_contract_sha256`。调用前会重新发现工具并核对契约，接口变化需要重新审查；不要自动接受发现命令输出的新指纹。
- `env_vars` 只列出允许传给子进程的环境变量名称；凭据通过启动 Agent 时的进程环境提供。仅写进 `.env` 不等于已导出到子进程，配置中也不接受明文 `env` 密钥。SDK 仍会提供运行所需的少量系统环境变量。
- 工具结果转换为统一状态，并附 `server_id / remote_name` 来源；处理结构化输出校验、脱敏和限长。超时或异常返回错误，当前不自动重试调用。

契约哈希用于发现接口结构变化，`read_only_hint` 是声明；两者都不能证明程序行为安全。本地 MCP 子进程没有被本模块沙箱隔离，必须审查程序和数据源权限。已有内置写工具仍按原策略处理，新增 MCP 工具只开放只读能力。

实现入口：[工具适配](serverAgentProgarm/app/tools/mcp.py)、[客户端](serverAgentProgarm/app/mcp/client.py)、[配置校验](serverAgentProgarm/app/mcp/config.py)。协议背景见 [MCP 架构说明](https://modelcontextprotocol.io/docs/learn/architecture)。

## 历史修复案例检索（RAG）

`RemediationContext` 绑定工单、调查快照和审批信息；修复后记录执行与 Verifier 的检查证据。已验证案例可以进入本地索引；缺失工单或修复上下文的记录隔离，失败案例保留为失败观察或聚合统计，不作为成功修复经验。这里的“已验证”只表示预设后置条件恢复，不能证明模型推断的根因正确。

检索使用 SQLite FTS5 / BM25、Ollama 向量和 RRF 融合排序，结果附案例及工单来源。Ollama 不可用时可降级为关键词检索；索引尚未建立时会返回错误，不能把它当成“没有历史故障”。历史参考不能代替本次实时检查，也不授予执行权限。

`RECOVERY_RAG_ENABLED` 的代码默认值是 `true`，`.env.example` 与之一致；设为 `false` 可关闭调查入口的检索接入及 Runner 自动建索引。默认使用本地 Ollama 和 `qwen3-embedding:0.6b`；向量服务需另行安装并准备模型。`hash` provider 仅用于离线测试，不代表真实语义向量。

在已配置数据库的 `serverAgentProgarm` 目录执行：

```bash
uv run serveragent knowledge cases
uv run serveragent knowledge sync
uv run serveragent knowledge search-cases "nginx 服务不可用" --service nginx
uv run serveragent knowledge revoke-case 12 --reason "案例内容已过时"
# 撤销后重建派生索引，避免继续检索到旧内容
uv run serveragent knowledge sync

# 纯离线合成语料评测，不访问 Ollama / LLM / SSH
uv run python -m scripts.eval_rag --embedding-provider hash --json
```

自治 Runner 在修复完成后触发进程内后台同步，包含事件合并、延迟和有限重试；它不是跨进程任务队列。CLI 可用于手动同步和核查。 当前 worker 退出窗口可能漏掉一次新通知，待索引案例会保留在数据库中，需后续通知、进程重启或手动运行 `knowledge sync` 补偿；案例生成也尚未强制校验所有验证证据字段的完整性。评测比较不检索、全量上下文、关键词、向量和混合检索，合成测试不能作为线上准确率或优化收益。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `RECOVERY_RAG_ENABLED` | `true` | 调查入口接入检索，允许 Runner 自动索引 |
| `RECOVERY_INDEX_PATH` | `.knowledge/recovery.sqlite` | 可重建的派生索引 |
| `RECOVERY_EMBEDDING_PROVIDER` | `ollama` | `ollama`，或仅供离线实验的 `hash` |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | 本地向量服务 |
| `RECOVERY_EMBEDDING_MODEL` | `qwen3-embedding:0.6b` | 向量模型 |
| `RECOVERY_EMBEDDING_TIMEOUT_SECONDS` | `30` | 向量请求超时，秒 |
| `RECOVERY_TOP_K` | `5` | 检索返回条数 |
| `RECOVERY_DENSE_MIN_SCORE` | `0.5` | 向量余弦相似度阈值 |
| `RECOVERY_CANDIDATE_LIMIT` | `20` | 候选数上限 |
| `RECOVERY_RRF_K` | `60` | 融合排序常数 |
| `RECOVERY_CONTEXT_MAX_CHARS` | `6000` | 检索片段字符预算 |
| `RECOVERY_CASE_ORIGIN` | `real` | 案例来源标签；实验应显式区分 |
| `RECOVERY_AUTO_INDEX_ENABLED` | `true` | Runner 自动后台同步开关 |
| `RECOVERY_INDEX_DEBOUNCE_SECONDS` | `3` | 合并同步事件的等待时间 |
| `RECOVERY_INDEX_RETRY_SECONDS` | `30` | 后台失败重试间隔 |
| `RECOVERY_INDEX_MAX_ATTEMPTS` | `3` | 每轮后台同步最大尝试次数 |

`RECOVERY_EMBEDDING_BATCH_SIZE` 当前虽存在于配置，尚未用于向量调用分批，不会改变请求批次。`.knowledge/`、业务数据库和案例数据均不进入 Git。

实现入口：[案例生成](serverAgentProgarm/app/knowledge/case_service.py)、[检索索引](serverAgentProgarm/app/knowledge/retriever.py)、[检索工具](serverAgentProgarm/app/tools/knowledge.py)。

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
| `get_service_details` | 服务状态、主进程及 unit 路径 | `systemctl show <service> --property=ActiveState,SubState,MainPID,ExecMainStartTimestamp,FragmentPath --no-pager` |
| `get_top_processes` | CPU 排名前列进程 | `ps -eo pid,comm,%cpu,%mem,rss --sort=-%cpu \| head -n 15` |
| `get_listening_ports` | TCP 监听地址与端口 | `ss -lntH` |

历史检索工具 `search_recovery_cases` 在 RAG 启用时注册；外部 MCP 工具通过准入后注册。二者都不是新增的 SSH 采集命令。

### 修复写入（medium 风险，默认需审批）

| 工具 | 用途 | 远端命令 |
|---|---|---|
| `restart_service` | 重启 systemd 服务 | `sudo -n systemctl restart <service>` |

### 内置 Runbook

| Runbook | 动作 | 后置验证 |
|---|---|---|
| `nginx_restart` | 重启 nginx | nginx active + 80 端口监听 |
| `docker_restart` | 重启 docker daemon（影响全部容器） | docker active + 3306 端口监听 |

输入约束：服务名白名单字符集（字母数字`._-`）、磁盘路径必须绝对路径且拒绝 `..`、端口 1-65535、日志行数 1-200。

### Runbook 怎么工作

Runbook 不是让 LLM 自由生成 shell 命令，而是一条受控的修复白名单：

1. 调查器只把 `name` 和 `trigger` 交给 LLM；LLM 最后只能返回某个已登记的 `name`，或返回 `null`。
2. Runner 用这个名字从 `RUNBOOKS` 中精确查找预案。名字不在白名单中时不会执行。
3. `plan` 只执行一个已经注册的 Tool，参数来自代码中的固定字典，不接受 LLM 临时改写。
4. Tool 成功后，Verifier 依次执行 `postcondition.checks` 中的只读检查；每个 `expect` 键值都匹配才算 `verified`。
5. 如果 `plan` 使用的是 medium/high 风险 Tool，仍然要经过权限模式和审批流程；Runbook 不会绕过权限闸门。

`trigger` 只是给 LLM 的适用场景提示，不是安全校验；`description` 和 `risk_note` 是预案元数据。当前版本的 `plan` 不支持 `${...}` 占位符、运行时参数或多步 `plan` 列表；一个 Runbook 是“一次 Tool 调用 + 多个后置检查”。

### 自定义 Runbook：复用现有 Tool

如果只是为另一个 systemd 服务增加重启预案，不需要写新 Tool。编辑 `serverAgentProgarm/app/remediation/runbooks.py`，把新的 `Runbook` 加入 `RUNBOOKS` 列表：

```python
Runbook(
    name="api_restart",  # 必须唯一；LLM 返回的字符串必须完全相同
    description="重启 api 服务",
    trigger="适用于 api 服务 inactive/failed，或 8080 端口不通的场景",
    plan={
        "tool": "restart_service",  # 必须是已注册 Tool
        "args": {"service": "api"},
    },
    postcondition={
        "checks": [
            {
                "tool": "get_service_status",  # 必须是已注册的只读 Tool
                "args": {"service": "api"},
                "expect": {"active": True},  # 必须匹配 Tool 返回 data 的键值
            },
            {
                "tool": "tcp_probe",
                "args": {"port": 8080},
                "expect": {"port_open": True},
            },
        ]
    },
    risk_note="重启期间 api 短暂不可用",
),
```

操作步骤：

1. 在 `RUNBOOKS` 列表中加入上面的对象，确保 `name` 不重复。
2. 确认目标机存在 `api.service`，并把实际监听端口写入 `tcp_probe` 检查；不需要的检查可以删除。
3. 如果 `api` 不在目标机允许重启的 sudoers 白名单中，按“目标服务器权限”章节增加一条精确命令。
4. 先用测试机和 `auto` 模式手动验证：

   ```bash
   cd serverAgentProgarm
   uv run python demo/run_runbook.py api_restart
   ```

5. 生产使用建议保持 `POLICY_MODE=standard`：执行后运行 `uv run serveragent approvals` 查看审批单，批准 `uv run serveragent approve <审批单ID>`；自治 Runner 会在批准后的下一轮继续做后置验证。

后置检查的 `expect` 必须对应工具实际返回的 `data`。例如 `get_service_status` 返回 `active`，`tcp_probe` 返回 `port_open`；写成不存在的字段会导致验证失败。

### 按环境配置服务预案

`get_runbooks()` 会合并内置 `RUNBOOKS` 与进程环境变量 `RECOVERY_SERVICE_PORTS` 中的服务端口映射，例如：

```bash
export RECOVERY_SERVICE_PORTS=mysql:3306,redis:6379
```

Windows PowerShell 使用 `$env:RECOVERY_SERVICE_PORTS="mysql:3306,redis:6379"`。该项直接由 `os.getenv` 读取，仅写入 `.env` 不会自动生效。

映射会生成固定参数的 `<service>_restart` 预案，并检查服务 active 与对应端口。无效项及重名项会跳过；配置不会授予 sudo 权限，目标机仍需逐条允许精确的重启命令。仅配置 `RECOVERY_SERVICE_PORTS` 不会把服务加入 `WATCHED_SERVICES` 周期监控列表。

## 自定义工具

内置 SSH 工具通过注入的 SSHClient 执行远端命令。新增内置能力 = 定义 Tool + 注册，不在 Agent / Web / CLI 里直接调 SSH。

```python
# 新建 app/tools/custom.py
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

然后必须在所有入口共用的装配点 `app/runtime_deps.py` 注册；否则 Runbook 的 `plan.tool` 或后置检查找不到这个工具：

```python
from app.tools.custom import build_custom_tools

for tool in (
    build_readonly_tools(ssh)
    + build_custom_tools(ssh)
    + build_remediation_tools(ssh)
):
    registry.register(tool)
```

### 工具编写要求

1. handler 内做参数白名单校验，不把输入拼接成任意 shell
2. 只读工具 `risk_level="low"`；写工具显式声明 `medium`/`high`，不依赖默认值
3. `parameters` schema 与 handler 实际读取的字段一致
4. 输出限长脱敏：密码 / Token / Cookie / Authorization 头不得进入 LLM 上下文
5. 每个工具配 FakeSSH 测试（参数校验、命令内容、失败路径、危险输入拒绝）

### 新增写工具清单

如果 Runbook 的动作不是现有 Tool 能完成的，按下面顺序增加能力：

1. 在 `app/tools/remediation.py` 或自定义模块中定义 Tool，严格校验参数，并显式声明 `risk_level="medium"` 或 `"high"`。
2. 在 `app/runtime_deps.py` 注册 Tool；Runbook 的 `plan.tool` 必须与 `Tool.name` 完全一致。
3. 在目标机 sudoers 中只允许这一个精确命令，不使用 `ALL` 或通配符。
4. 在 `app/remediation/runbooks.py` 增加 Runbook，并使用只读 Tool 编写后置断言。
5. 为参数校验、实际 SSH 命令、失败路径和危险输入补 FakeSSH 测试。

`auto` 模式只自动放行 medium 风险；high 风险（例如关键服务）仍需审批。新增写工具应先在 `standard` 模式验证，确认审批、执行和后置验证都符合预期。

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

默认两个内置 Runbook 所需的最小授权：

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

当前调查器仍共享含内置写工具的 Registry；模型收到“只读调查”提示不能作为权限隔离，尤其应谨慎配置 `auto` 模式。MCP 新工具的只读准入不改变这一既有边界。

当前限制（部署前必读）：`User.role` 已建模但 RBAC 未强制执行，任何登录用户可访问审批 API——Web 只应暴露给可信用户群；生产使用需补 HTTPS、登录限流、HttpOnly Cookie 会话与角色控制。

## 测试

全离线，不连接真实服务器 / LLM / MySQL：

```bash
cd serverAgentProgarm
uv run pytest -q
```

- `FakeSSHClient`：按命令返回预置输出并记录全部调用（可断言"拒绝后什么都没执行"）
- 真实 stdio MCP 子进程：覆盖发现、调用、契约变化、参数范围、超时、清理和脱敏；业务数据仍为夹具
- RAG：案例证据、隔离与撤销、索引重建、检索降级和合成评测
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
│   ├── knowledge/      修复案例、索引、混合检索与后台同步
│   ├── llm/            OpenAI 兼容客户端
│   ├── mcp/            本地 stdio 客户端、准入配置与结果处理
│   ├── monitor/        采集与巡检
│   ├── remediation/    Runbook、断言验证
│   ├── runtime/        自治 Runner、调查器
│   ├── security/       权限、审批、认证、审计
│   ├── ssh/            SSH 通道
│   ├── storage/        SQLAlchemy 模型与数据库入口
│   ├── tools/          Tool 契约、注册表、内置工具
│   └── web/            FastAPI 门面
├── tests/              离线测试套件
├── demo/               演示与 MCP 离线完整链路
├── scripts/            合成 RAG 评测
├── mcp.example.json    不含本机路径的 MCP 配置模板
└── web/                Vue3 + Vite 前端
deploy/                 MySQL docker-compose
```

## 文档

- 使用、配置、Runbook 和权限边界：本 README
- English version：[README.en.md](README.en.md)
- Python 子项目说明：[serverAgentProgarm/README.md](serverAgentProgarm/README.md)
- `docs/` 是本地学习与设计记录，已加入 `.gitignore`，不会发布到 GitHub；因此不在这里提供线上链接。

## 声明

本项目按"确定性工程包裹 LLM 决策"的思路构建，可用于个人服务器受控运维场景，但尚未达到生产级控制平面标准：SSH 主机指纹校验、审批并发抢占、数据库迁移、RBAC 强制执行、数据保留策略等仍在待办中。在不可信网络或多人可访问环境中部署前，请先完成上述加固。
