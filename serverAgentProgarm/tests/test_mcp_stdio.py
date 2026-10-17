"""使用真实 SDK 和本地子进程，检查工具往返与进程释放；无网络和真实数据库。"""
import asyncio
import ctypes
import json
import os
from pathlib import Path
import sys
import time
import pytest
from app.mcp.client import discover_tools, invoke_tool, MCPConnectionError
from app.mcp.config import MCPConfig
from app.tools.mcp import build_mcp_tool

PROJECT = Path(__file__).resolve().parents[1]


def alive(pid):
    if os.name != "nt":
        try: os.kill(pid,0)
        except ProcessLookupError: return False
        return True
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle: return False
    try:
        code = ctypes.c_ulong()
        assert kernel.GetExitCodeProcess(handle,ctypes.byref(code))
        return code.value == 259
    finally:
        kernel.CloseHandle(handle)


def wrapped_server(tmp_path, body=None, timeout=10):
    journal = tmp_path / "pids.txt"
    wrapper = tmp_path / "server.py"
    prefix = f"import os\nfrom pathlib import Path\nwith Path({str(journal)!r}).open('a') as f: f.write(str(os.getpid())+'\\n')\n"
    code = body or f"import runpy\nrunpy.run_path({str(PROJECT / 'demo/mcp_dbdiag_server.py')!r}, run_name='__main__')\n"
    wrapper.write_text(prefix+code,encoding="utf-8")
    server = MCPConfig.model_validate_json(json.dumps({"servers":[{"id":"dbdiag",
        "command":sys.executable,"args":[str(wrapper)],"cwd":str(PROJECT),
        "timeout_seconds":timeout,"tools":[]}]})).servers[0]
    return server,journal


def bind(server, observed):
    from app.mcp.config import AllowedMCPTool
    allowed = AllowedMCPTool.model_validate_json(json.dumps({"remote_name":observed.name,
        "local_name":"mcp_dbdiag_get_db_connections","description":"只读数据库连接查询",
        "risk_level":"low","expected_contract_sha256":observed.contract_sha256,
        "allowed_arguments":{"database":["shop","empty"]}}))
    return server.model_copy(update={"tools":(allowed,)}),allowed


def assert_closed(journal):
    pids = [int(line) for line in journal.read_text().splitlines()]
    assert pids
    # 只检查自己启动的 PID；退出完成后不应留下 Server 子进程。
    assert all(not alive(pid) for pid in pids)
    return pids


def test_real_sdk_discovery_calls_and_original_executor(tmp_path, executor):
    server,journal=wrapped_server(tmp_path)
    catalog=asyncio.run(discover_tools(server))
    assert_closed(journal)
    observed=catalog[0]
    assert observed.name=="get_db_connections" and observed.output_schema is not None
    server,allowed=bind(server,observed)
    executor.registry.register(build_mcp_tool(server,allowed,observed))
    success=executor.execute(allowed.local_name,{"database":"shop"})
    assert success.status=="success"
    assert success.data["payload"]["active_connections"]==180
    assert success.data["payload"]["source"]=="fixture"
    assert success.data["source"]["remote_name"]=="get_db_connections"
    empty=executor.execute(allowed.local_name,{"database":"empty"})
    assert empty.status=="no_data"
    pids=assert_closed(journal)
    denied=executor.execute(allowed.local_name,{"database":"private"})
    assert denied.status=="error"
    assert assert_closed(journal)==pids  # 非法范围不启动新进程。


def test_invalid_protocol_stdout_is_hidden_and_process_is_closed(tmp_path, caplog):
    server,journal=wrapped_server(tmp_path,"import time\nprint('protocol-secret-sentinel',flush=True)\ntime.sleep(30)\n",timeout=0.5)
    with pytest.raises(MCPConnectionError) as error:
        asyncio.run(discover_tools(server))
    assert "protocol-secret-sentinel" not in str(error.value)+caplog.text
    assert_closed(journal)


def test_real_call_timeout_reaps_server_process(tmp_path):
    body = """import asyncio
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
server=MCPServer('slow-fixture')
@server.tool(annotations=ToolAnnotations(read_only_hint=True))
async def slow_query(database: str) -> dict:
    await asyncio.sleep(30)
    return {'active':180}
server.run(transport='stdio')
"""
    server,journal=wrapped_server(tmp_path,body)
    observed=asyncio.run(discover_tools(server))[0]
    server,allowed=bind(server,observed)
    server=server.model_copy(update={"timeout_seconds":1.5})
    result=asyncio.run(invoke_tool(server,allowed,observed,{"database":"shop"}))
    assert result.status=="error" and "未自动重试" in result.error
    assert_closed(journal)
