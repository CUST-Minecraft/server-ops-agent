"""原 Loop、执行器与入口的 MCP 接入回归。"""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from app.agent.loop import run_agent
from app.mcp.client import DiscoveredMCPTool, tool_contract_hash
from app.mcp.config import load_mcp_config
from app.tools.base import ToolResult
from tests.conftest import FakeLLM
from tests.test_mcp_config import config_payload

SCHEMA = {"type":"object","properties":{"database":{"type":"string"}},
          "required":["database"],"additionalProperties":False}


@pytest.fixture()
def enabled(tmp_path, monkeypatch, db, fake_ssh):
    import app.runtime_deps as deps
    from app.tools import mcp as adapter
    payload = config_payload(tmp_path)
    payload["servers"][0]["tools"][0]["expected_contract_sha256"] = tool_contract_hash(SCHEMA,None)
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps(payload),encoding="utf-8")
    monkeypatch.setenv("MCP_ENABLED","true")
    monkeypatch.setenv("MCP_CONFIG_PATH",str(path))
    monkeypatch.setenv("RECOVERY_RAG_ENABLED","false")
    monkeypatch.setattr(deps,"SSHClient",lambda:fake_ssh)
    monkeypatch.setattr(deps,"SessionLocal",db)
    async def discover(_):
        return [DiscoveredMCPTool("get_connections",SCHEMA,None,tool_contract_hash(SCHEMA,None))]
    async def invoke(server,allowed,observed,args,**_):
        return ToolResult(status="success",data={"source":{"transport":"mcp","server_id":server.id},
            "payload":{"active":180,"source":"fixture"}})
    monkeypatch.setattr(adapter,"discover_tools",discover)
    monkeypatch.setattr(adapter,"invoke_tool",invoke)
    return deps


def test_agent_only_runtime_explicitly_registers_mcp(enabled):
    try:
        executor,registry,_ = enabled.build_executor_and_approvals(include_mcp=True)
    except TypeError:
        pytest.fail("公共装配尚未支持 MCP")
    assert "mcp_dbdiag_get_connections" in registry.names()
    assert executor.execute("mcp_dbdiag_get_connections",{"database":"shop"}).status == "success"
    _,base_registry,_ = enabled.build_executor_and_approvals()
    assert "mcp_dbdiag_get_connections" not in base_registry.names()


def test_original_loop_backfills_mcp_result_and_permission_audit(enabled, db):
    from app.storage.models import AuditLog
    executor,registry,_ = enabled.build_executor_and_approvals(include_mcp=True)
    llm=FakeLLM([("tool_calls",[("mcp_dbdiag_get_connections",'{"database":"shop"}',"mcp-call-1")]),
                 ("stop","连接数为 180。")])
    messages=[{"role":"user","content":"检查数据库"}]
    assert run_agent(llm,executor,registry,messages) == "连接数为 180。"
    observation=next(m for m in messages if m.get("tool_call_id")=="mcp-call-1")
    body=json.loads(observation["content"])
    assert body["data"]["source"]["transport"] == "mcp"
    with db() as session:
        assert session.query(AuditLog).filter_by(tool="mcp_dbdiag_get_connections").count()==1


def test_web_chat_assembles_and_executes_mcp_in_worker_threads(enabled, monkeypatch):
    from app.web import app as web
    from app.agent import loop, memory
    from app.llm import llm_client
    from app.agent import system_prompt
    monkeypatch.setattr(llm_client,"LLMClient",lambda:object())
    monkeypatch.setattr(memory,"load_memories",lambda _:"")
    monkeypatch.setattr(system_prompt,"get_system_prompt",lambda _:"test")
    builder_calls=[]
    original=enabled.build_executor_and_approvals
    def builder(**kwargs):
        with pytest.raises(RuntimeError): asyncio.get_running_loop()
        builder_calls.append(kwargs)
        return original(**kwargs)
    monkeypatch.setattr(enabled,"build_executor_and_approvals",builder)
    def agent(llm,executor,registry,messages,**_):
        with pytest.raises(RuntimeError): asyncio.get_running_loop()
        assert executor.execute("mcp_dbdiag_get_connections",{"database":"shop"}).status=="success"
        return "MCP 查询完成"
    monkeypatch.setattr(loop,"run_agent",agent)
    monkeypatch.setattr(web,"_persist_chat",lambda *_:None)
    class Request:
        async def json(self):
            return {"session_id":"mcp-test","messages":[{"role":"user","content":"查数据库"}]}
    async def call():
        response=await web.chat_stream(Request(),SimpleNamespace(id=7,username="test"))
        return [chunk async for chunk in response.body_iterator]
    chunks=asyncio.run(call())
    assert builder_calls==[{"include_mcp":True}]
    assert any("MCP" in str(chunk) for chunk in chunks)


def test_cli_chat_uses_mcp_enabled_runtime(enabled, monkeypatch):
    from app import cli
    from app.agent import loop, memory
    from app.llm import llm_client
    from app.storage import db as storage
    from typer.testing import CliRunner
    monkeypatch.setattr(storage,"init_db",lambda:None)
    monkeypatch.setattr(cli,"_authenticate_cli_user",lambda *_:SimpleNamespace(id=7,username="alice"))
    monkeypatch.setattr(cli,"_persist_cli_chat",lambda *_:None)
    monkeypatch.setattr(llm_client,"LLMClient",lambda:object())
    monkeypatch.setattr(memory,"load_memories",lambda _:"")
    calls=[]
    original=enabled.build_executor_and_approvals
    def builder(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)
    monkeypatch.setattr(enabled,"build_executor_and_approvals",builder)
    def agent(llm,executor,registry,messages,**_):
        assert executor.execute("mcp_dbdiag_get_connections",{"database":"shop"}).status=="success"
        return "MCP 查询完成"
    monkeypatch.setattr(loop,"run_agent",agent)
    result=CliRunner().invoke(cli.app,["chat"],input="alice\npassword\n检查数据库\nq\n")
    assert result.exit_code==0, result.exception
    assert calls==[{"include_mcp":True}]
    assert "MCP 查询完成" in result.output




def test_runner_startup_passes_mcp_registry_to_investigator(enabled, monkeypatch, db):
    from app.runtime import runner
    monkeypatch.setattr(runner,"setup_logging",lambda:None)
    monkeypatch.setattr(runner,"init_db",lambda:None)
    monkeypatch.setattr(runner,"SessionLocal",db)
    monkeypatch.setattr(runner,"LLMClient",lambda:object())
    monkeypatch.setattr(runner,"_build_recovery_sync_coordinator",lambda _:None)
    seen=[]
    def tick(collector, detector, service, approvals, investigator, *_):
        assert "mcp_dbdiag_get_connections" in investigator.registry.names()
        seen.append(True)
        raise KeyboardInterrupt
    monkeypatch.setattr(runner,"tick",tick)
    with pytest.raises(KeyboardInterrupt): runner.run()
    assert seen==[True]


def test_mcp_catalog_command_requires_no_core_settings(enabled, monkeypatch):
    from app import cli
    from typer.testing import CliRunner
    import app.mcp.client as client
    from app.tools import mcp as adapter
    monkeypatch.setattr(client,"discover_tools",adapter.discover_tools)
    def forbidden(): raise AssertionError("不应启动 SSH/数据库/LLM 装配")
    monkeypatch.setattr(cli,"setup_logging",forbidden)
    result=CliRunner().invoke(cli.app,["mcp","tools","--config",str(enabled.ServerSettings().mcp_config_path)])
    assert result.exit_code==0, result.output
    assert tool_contract_hash(SCHEMA,None) in result.output
    assert "get_connections" in result.output
    assert "mcp_dbdiag_get_connections" in result.output
