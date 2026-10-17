"""把外部 MCP 能力适配为项目 Tool，继续经过原 Executor 与 Policy。"""
import asyncio
import copy
import json
import logging
from jsonschema import SchemaError, ValidationError

from app.mcp.client import (MCPConnectionError, discover_tools, invoke_tool,
                            server_environment, validate_arguments, _check_schema)
from app.mcp.config import load_mcp_config
from app.mcp.result import redact_text, environment_secrets, clean_value
from app.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


def _run_sync(create_coroutine):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(create_coroutine())
    # 先检查再创建 coroutine，避免嵌套 event loop 或未 await 的警告。
    raise MCPConnectionError("同步 MCP 装配/调用应在线程中执行，请使用 asyncio.to_thread")


def _model_schema(value, secrets):
    if isinstance(value, dict): return {k: _model_schema(v, secrets) for k, v in value.items()}
    if isinstance(value, list): return [_model_schema(v, secrets) for v in value]
    if isinstance(value, str): return redact_text(value, secrets)
    return value


def build_mcp_tool(server, allowed, observed, *, invoker=None, max_chars=8000):
    if observed.name != allowed.remote_name or observed.contract_sha256 != allowed.expected_contract_sha256:
        raise ValueError("外部工具绑定或契约未通过准入")
    if observed.read_only_hint is False:
        raise ValueError("首版不准入声明为写操作的 MCP 工具")
    _check_schema(observed.input_schema, input_schema=True)
    # 每次工厂调用绑定自己的 Server/Tool，避免 for-loop 闭包都指向最后一项。
    env = server_environment(server)
    secrets = environment_secrets(env)
    schema = _model_schema(copy.deepcopy(observed.input_schema), secrets)
    schema["additionalProperties"] = False
    properties = schema.get("properties", {})
    for name, values in allowed.allowed_arguments.items():
        if name not in properties: raise ValueError("参数范围与工具 Schema 不匹配")
        encoded = lambda value: json.dumps(value, allow_nan=False, ensure_ascii=False)
        existing = properties[name].get("enum")
        permitted = [value for value in values if existing is None or
                     encoded(value) in {encoded(item) for item in existing}]
        if not permitted: raise ValueError("本地参数范围与 Server 枚举冲突")
        properties[name]["enum"] = permitted
        if "default" in properties[name] and encoded(properties[name]["default"]) not in {encoded(v) for v in permitted}:
            del properties[name]["default"]
            required = schema.setdefault("required", [])
            if name not in required:
                required.append(name)
    _check_schema(schema, input_schema=True)

    invoke = invoker or invoke_tool
    def handler(arguments):
        try:
            arguments = copy.deepcopy(arguments)
            validate_arguments(allowed, observed, arguments)
        except (ValueError, TypeError, ValidationError):
            return ToolResult(status="error", error="MCP 参数未通过 Schema 或本地范围校验")
        try:
            return _run_sync(lambda: invoke(server, allowed, observed, arguments, max_chars=max_chars))
        except MCPConnectionError:
            return ToolResult(status="error", error="MCP 同步调用不应在事件循环线程内执行")
        except Exception as error:
            return ToolResult(status="error", error=f"MCP 适配失败（{type(error).__name__}）")

    return Tool(name=allowed.local_name, description=allowed.description, parameters=schema,
                handler=handler, risk_level=allowed.risk_level,
                observability_filter=lambda args: clean_value(args, secrets))


def register_mcp_tools(registry, settings, *, discoverer=None):
    if not settings.mcp_enabled:
        return []
    config = load_mcp_config(settings.mcp_config_path)
    discover = discoverer or discover_tools
    aliases = {tool.local_name for server in config.servers for tool in server.tools}
    if aliases.intersection(registry.names()):
        raise ValueError("MCP 别名与已有工具重名")
    added = []
    for server in config.servers:
        try:
            catalog = _run_sync(lambda: discover(server))
        except MCPConnectionError as error:
            logger.warning("MCP Server %s 不可用（%s）；保留内置工具", server.id, type(error).__name__)
            continue
        by_name = {tool.name: tool for tool in catalog}
        for allowed in server.tools:
            observed = by_name.get(allowed.remote_name)
            if observed is None:
                logger.warning("MCP Server %s 缺少配置中的工具，跳过准入", server.id)
                continue
            try:
                tool = build_mcp_tool(server, allowed, observed,
                    max_chars=getattr(settings, "max_output_chars", 8000))
            except (ValueError, SchemaError, MCPConnectionError) as error:
                logger.warning("MCP Server %s 工具未准入（%s）", server.id, type(error).__name__)
                continue
            registry.register(tool)
            added.append(tool.name)
    return added
