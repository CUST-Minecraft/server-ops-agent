# serverAgentProgarm

ServerOpsAgent 的 Python 主程序。完整安装、配置、权限和运行边界见仓库根目录 [README.md](../README.md)；英文说明见 [README.en.md](../README.en.md)。

## 开发环境

```bash
uv sync --locked
cp .env.example .env
mkdir -p data
```

Windows 可使用 `New-Item -ItemType Directory -Force data` 创建数据库目录。目标机、数据库与日志配置包括 `SERVER_HOST / SERVER_USER / KEY_PATH / DB_URL / LOG_LEVEL`；调查、CLI chat 和 Web chat 另需 `API_KEY / BASE_URL / MODEL_ID`。凭据只放在本地环境或密钥管理系统。

默认 `MCP_ENABLED=false`、`RECOVERY_RAG_ENABLED=true`。RAG 的 Ollama 服务和模型需单独准备；不需要检索时可设 `RECOVERY_RAG_ENABLED=false`。

## MCP 只读工具

先运行完整离线链路：

```bash
uv run python -m demo.mcp_smoke
```

该演示使用真实 MCP 子进程和原 Agent Loop，模型与业务数据为模拟，不访问 SSH、真实 LLM 或业务数据库。

实际接入时复制 `mcp.example.json` 为 `mcp.json`，将 `command / cwd` 占位路径替换为本机绝对路径，再运行：

```bash
uv run serveragent mcp tools --config mcp.json
```

检查通过后才在本地配置启用 MCP。完整步骤、参数范围、契约指纹和环境变量边界见根 README 的“MCP 工具扩展”章节。MCP 不替代基础监控，也不开放外部写工具。

## 历史修复检索

已配置数据库后可查看案例和重建派生索引：

```bash
uv run serveragent knowledge cases
uv run serveragent knowledge sync
uv run serveragent knowledge search-cases "nginx 服务异常" --service nginx
```

历史案例仅供参考，执行仍由策略、审批和 Verifier 约束。首次建库与已有库升级的差别见根 README；`create_all` 不会迁移已有表。

## 目标机权限边界

SSH 使用受限账号，按需授予 journal 读取权限。内置写工具需要精确的 sudoers 白名单：

```text
opsagent ALL=(root) NOPASSWD: /usr/bin/systemctl restart nginx, /usr/bin/systemctl restart docker
```

路径以目标机 `command -v systemctl` 为准，文件权限 `0440`，并通过 `visudo -c` 校验。新增服务同样逐条授权；禁止全量 sudo、全量 systemctl 或 Docker 管理权限。当前 SSH 主机指纹校验仍需加固。

## 离线验证

```bash
uv run pytest -q
uv run python -m compileall -q app tests demo scripts
uv run python -m demo.mcp_smoke
uv run python -m scripts.eval_rag --embedding-provider hash --json
```

测试使用 FakeSSH、FakeLLM、内存 SQLite 和本地 MCP 子进程，不依赖真实服务器或模型服务。前端位于 `web/`，仍需按根 README 单独测试和构建；生成的 `static/` 不进入 Git。

`mcp.json`、`.env`、`.knowledge/`、业务数据库、记忆与日志均为本地数据；`docs/` 为私有学习记录，不发布到 GitHub。
