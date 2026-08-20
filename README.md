# ServerOpsAgent -- 智能服务器监测与自动运维 Agent

> 一个用"确定性工程"包裹 LLM 决策的单机自治运维 Agent：
> 通过 SSH 监控 Linux 服务器，发现异常自动调查、受控修复、闭环验证、全程留痕。

## 项目一句话

**LLM 只做一件事--像值班工程师一样调查和提议。** 低风险它自己干，高风险人签字，干什么都留痕，干完必须复检。

## 当前进度

> 本项目按 15 天课程逐步生长，当前完成至 **Day 3**。下方「已实现」是现在真正能跑的东西，「规划中」是后续天数的课程目标。

### 已实现（Day 1 - Day 3）

| 天 | 交付物 | 能做什么 |
|---|---|---|
| D1 | `config.py` / `SSHClient` / `LLMClient` / `setup_logging()` | 配置从 `.env` 注入；SSH 公钥登录目标机；OpenAI 兼容接口接通；统一日志入口 |
| D2 | `Tool` 契约 / 5 只读工具 / `ToolRegistry` | CPU/内存/磁盘/systemd 状态/journalctl 日志五件只读工具；注册表生成 OpenAI function schema |
| D3 | `ToolResult` 三态 / `ToolExecutor` / Agent Loop / `agent_chat.py` | 对话式 Agent 自主选工具、回填结果、迭代推理；执行器永不抛异常；max_steps 护栏 |

现在可以跑：`uv run python demo/agent_chat.py` -- 对它说"服务器资源状况如何"，它会自己调 `get_cpu_status` / `get_memory_usage` / `get_disk_usage` 并基于真实数据回答。

### 规划中（Day 4 - Day 15，课程目标）

```text
D4  持续巡检 + 持久化     D5  异常检测 + 开单   D6  权限闸门
D7  人工审批（HITL）      D8  受限修复 + 断言   D9  自治闭环
D10 CLI + 告警（10 天 MVP）D11 Web + MySQL      D12 注入/故障加固
D13 离线测试              D14 故障注入评测      D15 求职材料
```

完整 15 天全景表见 [docs/README.md](docs/README.md)。

## 学习本项目的正确姿势

这是一个**求职导向的学习型项目**，配套完整的 15 天课程（每天含教学 README、任务清单、学习笔记三件套）：

```text
docs/
├── README.md          课程入口（使用方法、15 天全景表、10 天冲刺路线）
├── day01/ ... day15/  每天三件套
├── research/          外部调研笔记（learn-claude-code / Hello-Agents / HolmesGPT）
└── design/            架构原则、演进图、5 篇 ADR
```

**从这里开始**：[docs/README.md](docs/README.md) -> [Day 1](docs/day01/README.md)

## 核心特性（终态目标）

> 以下为 15 天结束时的目标形态，当前尚未全部落地（见上方「当前进度」）。

- SSH 监控单台 Linux：CPU / 内存 / 磁盘 / systemd 服务状态 / 日志 / 端口探活
- 异常检测（阈值 + 连击防抖 + 开单去重）-> Incident 六态状态机
- Agent 调查循环（ReAct / OpenAI 兼容 function calling）：三态工具结果 + 迭代护栏 + 输出截断
- 四层权限闸门：deny 黑名单 -> 静态风险 -> 参数级动态升降 -> 模式策略（standard/strict/auto）
- Human-in-the-loop：审批单（参数哈希绑定 + TTL + append-only 审计），CLI / Web 双入口
- 受限修复：Runbook 白名单（LLM 选预案不发明动作）+ 后置条件断言式闭环验证
- 30+ pytest 离线全回归（FakeSSH / FakeLLM）；故障注入评测（检出率 / 定位准确率 / 修复成功率 / MTTR）

## 技术栈

Python 3.13 / 纯手写 Agent 循环（无重框架，见 [ADR-0005](docs/design/adr/0005-no-framework.md)）/ OpenAI 兼容接口（`openai` SDK，可切 GLM、Kimi、DeepSeek 等）/ paramiko / SQLAlchemy 2（SQLite -> MySQL 一行切换）/ FastAPI + Jinja2 / typer / pytest

## 快速开始

```bash
# 前置：目标 Linux 虚拟机（systemd + docker）配好 SSH 密钥登录；LLM API Key
cd serverAgentProgarm
uv sync
cp .env.example .env       # 填入配置项（当前需：服务器/SSH key/LLM key/DB_URL/LOG_LEVEL）
uv run python demo/agent_chat.py    # 当前的可对话 Agent
```

后续天数落地后将补：
- `uv run pytest` -- 离线全回归（Day 13）
- `serveragent run` -- 启动自治闭环（Day 10）

## 目标架构

```text
CLI / Web ──> ApprovalManager ──> ToolExecutor ──> 权限引擎(四层) ──> 工具 ──SSH──> Linux
                  ▲                    │                                            │
Runner 自治闭环 ──┤                    └── AuditLog                                 ▼
  采集->检测->Incident状态机->LLM调查->Runbook匹配->修复->断言验证->关单     MySQL（五张表，全程留痕）
                                        └── Alerter ──> 人
```

> 当前仅有「工具 ─SSH─> Linux」链路与 Agent Loop 已落地，其余节点随天数生长。

五条架构原则：`Agent != Tool`、`Tool != SSH`、`Permission != 执行`、`监控 != LLM`、`LLM != 安全边界`（展开见 [docs/design/README.md](docs/design/README.md)）

## 学习项目声明

本项目为**求职导向的学习型作品**：借鉴了 learn-claude-code、Hello-Agents、HolmesGPT 等项目的思想，所有设计决策（调研了什么 -> 考虑了什么 -> 拒绝了什么 -> 选择了什么 -> 为什么）见 [docs/research/](docs/research/) 与 [docs/design/adr/](docs/design/adr/)。
