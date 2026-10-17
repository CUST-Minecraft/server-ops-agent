"""MCP 适配必须经过原执行器，不能因新接入方式绕过权限。"""
import asyncio
import json
import sys
from types import SimpleNamespace
import pytest
from app.mcp.client import DiscoveredMCPTool, tool_contract_hash
from app.mcp.config import MCPConfig
from app.tools.base import ToolResult

try:
    from app.tools.mcp import build_mcp_tool, register_mcp_tools
except ModuleNotFoundError as error:
    if error.name != "app.tools.mcp": raise
    build_mcp_tool = register_mcp_tools = None

SCHEMA = {"type":"object","properties":{"database":{"type":"string"}},
          "required":["database"],"additionalProperties":False}


def config(tmp_path):
    payload = {"servers":[{"id":"dbdiag","command":sys.executable,"args":[],"cwd":str(tmp_path),
        "tools":[{"remote_name":"get_connections","local_name":"mcp_dbdiag_get_connections",
        "description":"只读查询","risk_level":"low","expected_contract_sha256":tool_contract_hash(SCHEMA,None),
        "allowed_arguments":{"database":["shop"]}}]}]}
    return MCPConfig.model_validate_json(json.dumps(payload)).servers[0]


def metadata():
    return DiscoveredMCPTool("get_connections",SCHEMA,None,tool_contract_hash(SCHEMA,None))


def feature():
    assert build_mcp_tool is not None, "MCP Tool 适配尚未实现"


def test_valid_call_uses_explicit_local_risk_and_bound_remote_source(tmp_path, executor):
    feature()
    server = config(tmp_path)
    calls = []
    async def invoke(s, allowed, observed, args, **_):
        calls.append((s.id, allowed.remote_name, args))
        return ToolResult(status="success",data={"active":180})
    tool = build_mcp_tool(server,server.tools[0],metadata(),invoker=invoke)
    executor.registry.register(tool)
    assert executor.execute(tool.name,{"database":"shop"}).status == "success"
    assert calls == [("dbdiag","get_connections",{"database":"shop"})]
    assert tool.risk_level == "low" and tool.parameters["properties"]["database"]["enum"] == ["shop"]


@pytest.mark.parametrize("args", [{"database":"private"},{"database":123},{"database":"shop","command":"restart"}])
def test_invalid_arguments_never_enter_invoker(tmp_path, executor, args):
    feature()
    server = config(tmp_path)
    calls = []
    async def invoke(*_, **__):
        calls.append(True)
        return ToolResult(status="success")
    tool = build_mcp_tool(server,server.tools[0],metadata(),invoker=invoke)
    executor.registry.register(tool)
    assert executor.execute(tool.name,args).status == "error"
    assert calls == []


def test_executor_denial_does_not_enter_mcp_handler(tmp_path, executor):
    feature()
    from app.security.policy import Decision, PermissionDecision
    server = config(tmp_path)
    calls = []
    async def invoke(*_, **__): calls.append(True)
    tool = build_mcp_tool(server,server.tools[0],metadata(),invoker=invoke)
    executor.registry.register(tool)
    executor.policy = SimpleNamespace(check=lambda *_: PermissionDecision(Decision.DENY,"测试拒绝"))
    assert executor.execute(tool.name,{"database":"shop"}).status == "error"
    assert calls == []


def test_registration_disabled_does_not_read_config_or_discover(monkeypatch, registry):
    feature()
    def forbidden(*_, **__): raise AssertionError("关闭时不能读取配置")
    monkeypatch.setattr("app.tools.mcp.load_mcp_config",forbidden)
    assert register_mcp_tools(registry,SimpleNamespace(mcp_enabled=False,mcp_config_path="missing")) == []


def test_transport_failure_keeps_existing_registry(tmp_path, registry):
    feature()
    from app.mcp.client import MCPConnectionError
    from app.tools import mcp as module
    server = config(tmp_path)
    async def discover(_): raise MCPConnectionError("不可用")
    module_config = SimpleNamespace(servers=[server])
    from unittest.mock import patch
    before = registry.names()
    with patch.object(module,"load_mcp_config",return_value=module_config):
        added = register_mcp_tools(registry,SimpleNamespace(mcp_enabled=True,mcp_config_path="mcp.json"),
                                   discoverer=discover)
    assert added == [] and registry.names() == before


def test_async_caller_is_rejected_without_unawaited_coroutine(tmp_path):
    feature()
    server = config(tmp_path)
    calls = []
    async def invoke(*_, **__): calls.append(True)
    tool = build_mcp_tool(server,server.tools[0],metadata(),invoker=invoke)
    async def caller(): return tool.handler({"database":"shop"})
    result = asyncio.run(caller())
    assert result.status == "error" and calls == []


def test_write_hint_and_bad_contract_do_not_build_a_readonly_tool(tmp_path):
    feature()
    server = config(tmp_path)
    for descriptor in [DiscoveredMCPTool("get_connections",SCHEMA,None,"b"*64),
                       DiscoveredMCPTool("get_connections",SCHEMA,None,tool_contract_hash(SCHEMA,None),False)]:
        with pytest.raises(ValueError): build_mcp_tool(server,server.tools[0],descriptor)



def test_short_environment_secret_is_redacted_from_model_schema(tmp_path, monkeypatch):
    server = config(tmp_path).model_copy(update={"env_vars":("API_KEY",)})
    monkeypatch.setenv("API_KEY", "abc123")
    schema = json.loads(json.dumps(SCHEMA))
    schema["properties"]["database"]["description"] = "连接提示 abc123"
    digest = tool_contract_hash(schema,None)
    allowed = server.tools[0].model_copy(update={"expected_contract_sha256":digest})
    tool = build_mcp_tool(server,allowed,DiscoveredMCPTool("get_connections",schema,None,digest))
    assert "abc123" not in json.dumps(tool.parameters)


def test_rejected_credentials_are_not_written_to_invocation_or_audit(tmp_path, executor, db):
    from app.security.policy import PermissionEngine
    from app.storage.models import AuditLog
    server = config(tmp_path)
    async def forbidden(*_, **__): raise AssertionError("不能调用")
    tool = build_mcp_tool(server,server.tools[0],metadata(),invoker=forbidden)
    executor.registry.register(tool)
    executor.policy = PermissionEngine(mode="standard")
    executor.session_factory = db
    result = executor.execute(tool.name,{"database":"shop", "connection":{"password":"sentinel-value"}})
    assert result.status == "error"
    assert "sentinel-value" not in result.invocation
    with db() as session:
        row=session.query(AuditLog).filter_by(tool=tool.name).one()
        assert "sentinel-value" not in json.dumps(row.args)



def test_separate_servers_with_same_remote_name_keep_their_bindings(tmp_path, executor):
    first=config(tmp_path)
    second_allowed=first.tools[0].model_copy(update={"local_name":"mcp_second_get_connections"})
    second=first.model_copy(update={"id":"second","tools":(second_allowed,)})
    calls=[]
    async def invoke(server,allowed,observed,args,**_):
        calls.append((server.id,allowed.local_name))
        return ToolResult(status="success")
    for server in [first,second]:
        executor.registry.register(build_mcp_tool(server,server.tools[0],metadata(),invoker=invoke))
    for name in [first.tools[0].local_name,second_allowed.local_name]:
        assert executor.execute(name,{"database":"shop"}).status=="success"
    assert calls==[("dbdiag",first.tools[0].local_name),("second",second_allowed.local_name)]


def test_registry_only_contains_allowed_matching_contracts(tmp_path, registry):
    from app.tools import mcp as module
    from unittest.mock import patch
    server=config(tmp_path)
    async def discover(_):
        return [metadata(),DiscoveredMCPTool("unapproved",SCHEMA,None,tool_contract_hash(SCHEMA,None))]
    settings=SimpleNamespace(mcp_enabled=True,mcp_config_path="unused")
    with patch.object(module,"load_mcp_config",return_value=SimpleNamespace(servers=[server])):
        assert register_mcp_tools(registry,settings,discoverer=discover)==[server.tools[0].local_name]
    assert "unapproved" not in registry.names()
    altered=server.tools[0].model_copy(update={"expected_contract_sha256":"f"*64,"local_name":"mcp_altered"})
    server=server.model_copy(update={"tools":(altered,)})
    with patch.object(module,"load_mcp_config",return_value=SimpleNamespace(servers=[server])):
        assert register_mcp_tools(registry,settings,discoverer=discover)==[]


def test_duplicate_alias_against_builtin_is_rejected_before_discovery(tmp_path, registry):
    from app.tools import mcp as module
    from unittest.mock import patch
    server=config(tmp_path)
    allowed=server.tools[0].model_copy(update={"local_name":registry.names()[0]})
    server=server.model_copy(update={"tools":(allowed,)})
    async def forbidden(_): raise AssertionError("不应启动外部进程")
    with patch.object(module,"load_mcp_config",return_value=SimpleNamespace(servers=[server])):
        with pytest.raises(ValueError):
            register_mcp_tools(registry,SimpleNamespace(mcp_enabled=True,mcp_config_path="unused"),discoverer=forbidden)



def test_scoped_default_does_not_duplicate_required_fields(tmp_path):
    from jsonschema import Draft202012Validator
    server=config(tmp_path)
    schema=json.loads(json.dumps(SCHEMA))
    schema["properties"]["database"]["default"]="private"
    digest=tool_contract_hash(schema,None)
    allowed=server.tools[0].model_copy(update={"expected_contract_sha256":digest})
    observed=DiscoveredMCPTool("get_connections",schema,None,digest)
    tool=build_mcp_tool(server,allowed,observed)
    Draft202012Validator.check_schema(tool.parameters)
    assert tool.parameters["required"]==["database"]
    assert "default" not in tool.parameters["properties"]["database"]
