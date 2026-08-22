# serverAgentProgarm

Server-Agent 学习项目主程序（15 天计划）。架构与进度见 `../docs/`。

## 快速开始

```bash
uv sync                 # 安装依赖
cp .env.example .env    # 复制配置模板，再填真实值
uv run python -m app.ssh.ssh_client   # 验证 SSH 链路
uv run python demo/agent_chat.py      # Day 3 起可跑对话式 Agent
```

## 环境准备

### 1. SSH 密钥（免密令牌）

Agent 要无人值守执行 shell，必须走**密钥认证**（paramiko 无法交互式输密码）。
原理：私钥留在发起方（本机 Windows），公钥装到目标方（Linux 虚拟机）。

**开发机（Windows）上生成密钥对**：

```bash
ssh-keygen -t ed25519 -f ~/.ssh/opsagent_key -N "" -C "server-ops-agent"
```

`-N ""` 表示私钥不加 passphrase（无人值守必需；生产环境应 passphrase + ssh-agent）。

**在目标机（虚拟机）上创建 opsagent 账号并装入公钥**：

```bash
sudo useradd -m -s /bin/bash opsagent
sudo mkdir -p /home/opsagent/.ssh
echo "<把 ~/.ssh/opsagent_key.pub 的内容贴在这里>" | sudo tee /home/opsagent/.ssh/authorized_keys
sudo chmod 700 /home/opsagent/.ssh
sudo chmod 600 /home/opsagent/.ssh/authorized_keys
sudo chown -R opsagent:opsagent /home/opsagent/.ssh
```

> `chmod` / `chown` 一行都不能省：权限太开放时 sshd 会**静默拒绝**密钥认证，
> 表现为公钥明明装了却仍然要密码。

### 2. sudoers 白名单（Day 6 权限模型的 OS 层兜底）

opsagent 不给全量 sudo，只放行课程需要的命令（nginx 走 systemctl，
MySQL 容器走 docker；容器名见 `../deploy/mysql/docker-compose.yml`）：

```bash
echo 'opsagent ALL=(root) NOPASSWD: /usr/bin/systemctl restart nginx, /usr/bin/systemctl start nginx, /usr/bin/systemctl stop nginx, /usr/bin/docker restart server-agent-mysql, /usr/bin/docker stop server-agent-mysql, /usr/bin/docker start server-agent-mysql' | sudo tee /etc/sudoers.d/opsagent
sudo chmod 440 /etc/sudoers.d/opsagent
sudo visudo -c   # 必须输出 parsed OK
```

> **禁止** `usermod -aG docker opsagent` 或白名单 `/usr/bin/docker`：
> 完整 docker 权限 ≈ root（`docker run -v /:/host` 可挂载宿主机文件系统）。
> 只放行针对单一容器的精确命令，锁死爆炸半径。

### 3. 配置 `.env`

```bash
SERVER_HOST=192.168.100.128
SERVER_PORT=22
SERVER_USER=opsagent
KEY_PATH=C:/Users/T5A/.ssh/opsagent_key   # Windows 下必须写全路径，~ 不展开
DB_URL=...
API_KEY=...
BASE_URL=...
MODEL_ID=...
```

### 4. 验证链路

```bash
# 开发机上：手工 ssh 免密验证（排障第一步）
ssh -i ~/.ssh/opsagent_key opsagent@192.168.100.128 "uptime"

# 项目代码验证：输出结构化 dict 且 exit_code=0 即通
uv run python -m app.ssh.ssh_client
```

## 常见问题

| 症状 | 原因 | 解法 |
|---|---|---|
| 仍要密码，公钥已装 | 服务器上 `.ssh` 非 700 或 `authorized_keys` 非 600 | 回目标机重跑 chmod / chown |
| `AuthenticationException` | `KEY_PATH` 写了 `~`（Windows 不展开）、密钥路径错 | `.env` 里写全路径；先手工 `ssh -i` 验证 |
| 连接超时 | 虚拟机没开 / IP 变了 | 目标机上 `ip a` 确认 IP，更新 `.env` |
| `Permission denied`（exit_code=1，但能连上） | opsagent 权限不足，**这是安全模型在正常工作** | 换有权限的命令，或按需扩 sudoers 白名单 |
