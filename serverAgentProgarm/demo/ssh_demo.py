"""Day 1 示例：paramiko 最小 SSH 连接与命令执行。

运行前提：pip install paramiko；.env 已配好 SERVER_* 三项
这个文件演示概念；项目里真正的实现在 app/ssh/client.py
（增加了连接复用、超时、错误分类）。
"""

import os
import time

import paramiko


def run_command(host: str, port: int, user: str, key_path: str, cmd: str) -> None:
    client = paramiko.SSHClient()
    # 学习环境自动接受主机指纹；生产环境应预置 known_hosts
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=host,
            port=port,
            username=user,
            key_filename=key_path,
            timeout=10,
        )
        start = time.monotonic()
        _, stdout, stderr = client.exec_command(cmd, timeout=10)
        exit_code = stdout.channel.recv_exit_status()
        elapsed = int((time.monotonic() - start) * 1000)
        print(f"命令: {cmd}")
        print(f"退出码: {exit_code}  耗时: {elapsed}ms")
        print(f"stdout: {stdout.read().decode().strip()}")
        err = stderr.read().decode().strip()
        if err:
            print(f"stderr: {err}")
    finally:
        client.close()


if __name__ == "__main__":
    key = os.path.expanduser(os.environ.get("KEY_PATH", "~/.ssh/server_agent_key"))
    run_command(
        host=os.environ.get("SERVER_HOST", "192.168.56.10"),
        port=22,
        user="opsagent",
        key_path=key,
        cmd="uptime && df -h / | tail -1",
    )
