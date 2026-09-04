# serverAgentProgarm

ServerOpsAgent 的 Python 主程序目录。项目定位、内置工具、自定义工具契约和目标机权限边界见仓库根目录的 [README.md](../README.md)。

这里保留开发环境和运行边界说明；完整部署、初始化和日常操作手册暂不放在本文件中。

## 开发环境

```bash
uv sync
cp .env.example .env
```

`.env` 至少需要提供：

```text
SERVER_HOST
SERVER_PORT
SERVER_USER
KEY_PATH
DB_URL
LOG_LEVEL
API_KEY
BASE_URL
MODEL_ID
```

目标机地址、SSH 私钥和 LLM API Key 只放在本地环境变量或密钥管理系统中，不提交到 Git。

## 目标机权限边界

Agent 通过 SSH 使用受限的 `opsagent` 账号。目标机只需要允许 Agent 主机访问 TCP `22`，并安装公钥认证；不要给 `opsagent` 全量 root、全量 sudo 或 Docker 管理权限。

只读工具执行以下命令，不需要 sudo：

```text
top -bn1 | grep 'Cpu(s)' ; uptime
free -m
systemctl is-active <validated service>
```

如果需要完整读取 systemd journal，应优先配置 per-service 访问；将 `opsagent` 加入 `systemd-journal` 会扩大日志可见范围，可能读取到个人网站的敏感数据。

当前写工具只执行以下精确命令：

```text
sudo -n systemctl restart nginx
sudo -n systemctl restart docker
```

匹配的 sudoers 规则：

```text
opsagent ALL=(root) NOPASSWD: /usr/bin/systemctl restart nginx, /usr/bin/systemctl restart docker
```

实际路径以目标机的 `command -v systemctl` 为准。sudoers 文件使用 `0440` 权限，并通过 `visudo -c` 校验。

禁止使用：

```text
opsagent ALL=(root) NOPASSWD: ALL
opsagent ALL=(root) NOPASSWD: /usr/bin/systemctl
opsagent ALL=(root) NOPASSWD: /usr/bin/docker
usermod -aG docker opsagent
```

当前 SSH 客户端仍需要生产化补充 Host Key pinning；在不可信网络中使用前，必须确认目标机指纹校验方案。

## 离线验证

测试不连接真实服务器、LLM 或 MySQL：

```bash
uv run pytest -q
uv run python -m compileall -q app tests
```

Web 前端位于 `web/`，构建产物写入上级 `static/`，该目录不进入 Git。生产或演示前需要单独执行前端构建。
