"""Day 2 演示：注册 5 个只读工具并程序化调用（同时验收你的 Registry 实现）。"""
from app.ssh.ssh_client import SSHClient
from app.tools.builtin import build_readonly_tools
from app.tools.registry import ToolRegistry

if __name__ == "__main__":
    registry = ToolRegistry()
    for tool in build_readonly_tools(SSHClient()):
        registry.register(tool)

    print("已注册工具:", registry.names())

    import json
    print("\nget_cpu_status 的 schema:")
    print(json.dumps(registry.schemas()[0], ensure_ascii=False, indent=2))

    tool = registry.get("get_service_status")
    print("\n直接调用 get_service_status({\"service\": \"ssh\"}):")
    print(tool.handler({"service": "ssh"}))