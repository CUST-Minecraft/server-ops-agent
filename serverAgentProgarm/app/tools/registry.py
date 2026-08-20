"""工具注册表：登记、查找、生成 LLM 可读的 schema 清单。"""
from app.ssh.ssh_client import SSHClient
from app.tools.base import Tool
from app.tools.builtin import build_readonly_tools


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"工具重名: {tool.name}")   # 歧义在注册时就炸，不等到调用时猜
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def schemas(self) -> list[dict]:
        """生成 OpenAI 格式的工具清单。Day 3 起，这个列表会被传给 LLMClient.chat(tools=...)。"""
        tools_list = []
        for tool in self._tools.values():
            tools_list.append(
                {
                    "type" : "function",
                    "function" : {
                        "name" : tool.name,
                        "description" : tool.description,
                        "parameters": tool.parameters,
                    }
                }
            )
        return tools_list


if __name__ == "__main__":
    tool_registry = ToolRegistry()
    ssh = SSHClient()
    tools_list_   = build_readonly_tools(ssh)
    for tool_ in tools_list_:
        tool_registry.register(tool_)
    print(tool_registry.schemas()[0])
    print(tool_registry.schemas()[0]["function"]["handler"]({}))
