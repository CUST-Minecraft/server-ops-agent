"""独立只读 MCP Server；连接数为教学夹具，替换本文件的数据源即可接真实查询。"""
from typing import Literal
from pydantic import BaseModel, Field
from mcp.server import MCPServer
from mcp.types import ToolAnnotations

server = MCPServer("dbdiag-demo")


class ConnectionSnapshot(BaseModel):
    status: Literal["success", "no_data"]
    database: str
    active_connections: int | None = Field(default=None, ge=0)
    max_connections: int | None = Field(default=None, ge=1)
    source: Literal["fixture"] = "fixture"


@server.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_db_connections(database: Literal["shop", "empty"]) -> ConnectionSnapshot:
    """只读查询教学连接数；shop 有合成数据，empty 没有记录。"""
    if database == "empty":
        return ConnectionSnapshot(status="no_data", database=database)
    return ConnectionSnapshot(status="success", database=database,
                              active_connections=180, max_connections=200)


if __name__ == "__main__":
    # stdout 只交给 SDK 输出协议消息，诊断日志使用 stderr。
    server.run(transport="stdio")
