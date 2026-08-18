"""Day 2 最小 Demo：一个工具 = 一个函数 + 一份说明书。

运行：uv run python demo/minimal_tool.py
"""
from app.ssh.ssh_client import SSHClient
from app.tools.base import Tool


def make_uptime_tool(ssh: SSHClient) -> dict:
    """把'查 uptime'包装成一个自描述的工具。"""
    def handler(args: dict) -> dict:
        r = ssh.run("uptime")
        return {"uptime": r["stdout"], "ok": r["exit_code"] == 0}

    return {
        "name": "get_uptime",                          # 名字：给程序按名调用
        "description": "查询服务器运行时长与 1/5/15 分钟平均负载",  # 说明书：给 LLM 看
        "parameters": {"type": "object", "properties": {}},       # 参数格式
        "handler": handler,                            # 真正干活的函数
    }



if __name__ == "__main__":
    ssh = SSHClient()
    tool = make_uptime_tool(ssh)

    tool2 = Tool(
        name="get_uptime",
        description="查询服务器运行时长与平均负载",
        parameters={"type": "object", "properties": {}},
        handler=tool["handler"],  # 复用刚才的 handler
    )

    print(tool2.handler({}))