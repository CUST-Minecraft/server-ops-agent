# ServerOpsAgent -- 智能服务器监控与自主运维 Agent

> 一个用"确定性工程"包裹 LLM 决策的单机自治运维 Agent：
> 通过 SSH 监控 Linux 服务器，发现异常自动调查、受控修复、闭环验证、全程留痕。

## 项目一句话

**LLM 只做一件事--像值班工程师一样调查和提议。** 低风险它自己干，高风险人签字，干什么都留痕，干完必须复检。

## 核心特性（目标 MVP）

- SSH 监控单台 Linux：CPU / 内存 / 磁盘 / 进程 / systemd 服务 / 日志
- 异常检测（阈值 + 持续确认防抖）-> Incident 生命周期管理
- Agent 调查循环（ReAct）：工具调用 + 结构化结果 + 护栏
- 四层权限引擎：deny 硬规则 -> 静态风险 -> 参数级动态风险 -> 阈值策略
- Human-in-the-loop：审批单绑定参数哈希、支持过期、CLI / Web 双入口
- 闭环验证：修复前声明后置条件，修复后确定性复检，失败重试与升级
- MySQL 持久化（事件溯源式审计）、FastAPI 状态/事件/审批页面、结构化事件报告

## 技术栈

Python 3.11+ / 纯 Python Agent 循环（无重框架）/ Anthropic 兼容 LLM 层（可切 GLM、Kimi、DeepSeek 等）/ paramiko / MySQL + SQLAlchemy（可切 SQLite 测试）/ FastAPI + Jinja2 / typer / pytest

## 当前状态

**Phase 1~3 已完成 -- 总体计划 + 15 天逐日学习文档 + 设计理由书就绪，进入 Phase 4 逐日实现。**

- [x] Phase 1：调研 + 总体计划（见 [docs/plan/](docs/plan/README.md)）
- [x] Phase 2：计划确认（用户免审通过，新增设计理由书要求）
- [x] Phase 3：day01~15 逐日学习文档（见 [docs/day01/README.md](docs/day01/README.md) 起每日推进）
- [ ] Phase 4：逐日实现（从 [Day 1](docs/day01/README.md) 开始）
- [ ] Phase 5：打磨 + 面试材料

## 快速导航

| 内容 | 位置 |
|---|---|
| 项目总体计划（A~R 全景） | [docs/plan/01-master-plan.md](docs/plan/01-master-plan.md) |
| 15 天日程（主执行版） | [docs/plan/03-schedule-15day.md](docs/plan/03-schedule-15day.md) |
| 10 天日程（备用版） | [docs/plan/02-schedule-10day.md](docs/plan/02-schedule-10day.md) |
| 双版本对比与推荐 | [docs/plan/04-plan-comparison.md](docs/plan/04-plan-comparison.md) |
| 外部调研笔记（8 篇） | [docs/plan/research/](docs/plan/research/) |
| **设计理由书（全局：为什么这么设计）** | [docs/design/design-rationale.md](docs/design/design-rationale.md) |
| 每日学习文档（Day 1~15，每天含 design.md 当日设计理念） | [docs/day01/README.md](docs/day01/README.md) ~ [docs/day15/README.md](docs/day15/README.md) |

## 架构一图流

```text
CLI / Web ──> Agent 核心进程 ──> Tool Registry ──> 权限引擎(四层) ──> 执行器 ──SSH──> Linux 被监控机
                  ▲                                                        │
监控调度器 ──> 检测器 ──> Incident 状态机 ──> 审批队列 <── 人工               ▼
                  └──────────── MySQL（事件溯源，一切可回放） <── ToolResult ┘
```

五条架构原则：`Agent != Tool`、`Tool != SSH`、`Permission != 执行`、`监控 != LLM`、`LLM != 安全边界`

## 学习项目声明

本项目为**求职导向的学习型作品**：借鉴了 Claude Code、HolmesGPT、OpenHands、SWE-agent、LangGraph、learn-claude-code 等项目的思想（详见调研笔记），所有设计决策均记录了"调研了什么 -> 考虑了什么 -> 拒绝了什么 -> 选择了什么 -> 为什么"，见 `docs/design/decisions/`（ADR，Phase 3 起产出）。
