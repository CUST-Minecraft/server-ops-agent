"""SDK stdio 通信；每次操作在同一异步任务内完成进入、使用和退出。"""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import hashlib
import json
import os

from jsonschema import Draft202012Validator, ValidationError
from mcp import Client, StdioServerParameters, stdio_client
from app.mcp.config import AllowedMCPTool, MCPServerConfig
from app.mcp.result import SENSITIVE_KEY, environment_secrets, normalize_mcp_result
from app.mcp.logging import safe_sdk_logs
from app.tools.base import ToolResult

MAX_PAGES = 20
MAX_TOOLS = 100


class MCPConnectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class DiscoveredMCPTool:
    name: str
    input_schema: dict
    output_schema: dict | None
    contract_sha256: str
    read_only_hint: bool | None = None


def tool_contract_hash(input_schema, output_schema) -> str:
    text = json.dumps({"input": input_schema, "output": output_schema}, sort_keys=True,
                      ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _check_schema(schema, *, input_schema=False):
    if not isinstance(schema, dict):
        raise ValueError("Schema 必须为对象")
    Draft202012Validator.check_schema(schema)
    if input_schema:
        if schema.get("type") != "object" or any(k in schema for k in ("$ref", "$dynamicRef", "allOf", "anyOf", "oneOf")):
            raise ValueError("参数根 Schema 必须是直接定义的对象")
    def visit(node):
        if isinstance(node, dict):
            if input_schema and any(SENSITIVE_KEY.fullmatch(key) for key in node.get("properties", {})):
                raise ValueError("凭据应通过环境变量传入，不向模型提供凭据参数")
            for key, value in node.items():
                if key in {"$ref", "$dynamicRef"} and (not isinstance(value, str) or not value.startswith("#")):
                    raise ValueError("不允许外部 Schema 引用")
                visit(value)
        elif isinstance(node, list):
            for value in node: visit(value)
    visit(schema)


async def _list_all(client):
    result, names, cursors = [], set(), set()
    cursor = None
    for _ in range(MAX_PAGES):
        page = await client.list_tools(cursor=cursor)
        for raw in page.tools:
            if raw.name in names or len(result) >= MAX_TOOLS:
                raise ValueError("重复工具名或工具数超出上限")
            _check_schema(raw.input_schema, input_schema=True)
            if raw.output_schema is not None:
                _check_schema(raw.output_schema)
            names.add(raw.name)
            annotations = getattr(raw, "annotations", None)
            result.append(DiscoveredMCPTool(raw.name, raw.input_schema, raw.output_schema,
                tool_contract_hash(raw.input_schema, raw.output_schema),
                getattr(annotations, "read_only_hint", None)))
        cursor = page.next_cursor
        if cursor is None: return result
        if cursor in cursors: raise ValueError("分页 cursor 重复")
        cursors.add(cursor)
    raise ValueError("分页超出上限")


def server_environment(server):
    result = {"PYTHONUTF8": "1"}
    for name in server.env_vars:
        value = os.environ.get(name)
        if value is None:
            raise MCPConnectionError("MCP 所需环境变量未设置：" + name)
        result[name] = value
    return result


@asynccontextmanager
async def _open_client(server):
    params = StdioServerParameters(command=server.command, args=list(server.args),
        cwd=server.cwd, env=server_environment(server))
    # 外部程序 stderr 可能包含凭据，统一丢弃；返回给宿主的是固定错误类别。
    with safe_sdk_logs(), open(os.devnull, "w", encoding="utf-8") as errlog:
        transport = stdio_client(params, errlog=errlog)
        async with Client(transport, read_timeout_seconds=server.timeout_seconds) as client:
            yield client


async def discover_tools(server: MCPServerConfig, *, client_factory=None):
    factory = client_factory or _open_client
    try:
        async with asyncio.timeout(server.timeout_seconds):
            async with factory(server) as client:
                return await _list_all(client)
    except Exception as error:
        raise MCPConnectionError(f"MCP 发现失败（{type(error).__name__}）") from None


def validate_arguments(allowed: AllowedMCPTool, observed: DiscoveredMCPTool, arguments):
    if not isinstance(arguments, dict): raise ValueError("参数必须是对象")
    if len(json.dumps(arguments, ensure_ascii=False, allow_nan=False)) > 4000:
        raise ValueError("参数超出字符上限")
    properties = observed.input_schema.get("properties", {})
    if set(arguments) - set(properties): raise ValueError("不允许未知参数")
    Draft202012Validator(observed.input_schema).validate(arguments)
    for name, values in allowed.allowed_arguments.items():
        if name not in properties: raise ValueError("参数白名单与 Schema 不匹配")
        value = arguments.get(name, properties[name].get("default"))
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        if encoded not in {json.dumps(item, ensure_ascii=False, allow_nan=False) for item in values}:
            raise ValueError("参数超出本地允许范围")


async def invoke_tool(server, allowed, observed, arguments, *, client_factory=None, max_chars=8000):
    source = {"transport": "mcp", "server_id": server.id, "remote_name": allowed.remote_name}
    try:
        validate_arguments(allowed, observed, arguments)
        if observed.name != allowed.remote_name or observed.contract_sha256 != allowed.expected_contract_sha256:
            raise ValueError("工具绑定与本地契约不一致")
    except (ValueError, TypeError, ValidationError):
        return ToolResult(status="error", data={"source": source}, error="MCP 参数或工具绑定未通过校验")
    factory = client_factory or _open_client
    try:
        async with asyncio.timeout(server.timeout_seconds):
            async with factory(server) as client:
                catalog = await _list_all(client)
                current = next((item for item in catalog if item.name == allowed.remote_name), None)
                if current is None or current.contract_sha256 != allowed.expected_contract_sha256 or current.read_only_hint is False:
                    return ToolResult(status="error", data={"source": source}, error="MCP 工具缺失、契约变化或声明为写操作")
                raw = await client.call_tool(allowed.remote_name, arguments)
                if not raw.is_error and current.output_schema is not None:
                    Draft202012Validator(current.output_schema).validate(raw.structured_content)
                env = server_environment(server)
                secrets = environment_secrets(env)
                return normalize_mcp_result(raw, server_id=server.id, remote_name=allowed.remote_name,
                                            max_chars=max_chars, secret_values=secrets)
    except Exception as error:
        return ToolResult(status="error", data={"source": source},
                          error=f"MCP 调用失败（{type(error).__name__}）；未自动重试")
