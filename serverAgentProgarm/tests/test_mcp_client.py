"""MCP 生命周期、契约与结果边界；不连接外部服务。"""
import asyncio
import json
import sys
from types import SimpleNamespace
import pytest
from app.mcp.config import MCPConfig

try:
    from app.mcp.client import (MCPConnectionError, discover_tools, invoke_tool,
                                tool_contract_hash)
    from app.mcp.result import normalize_mcp_result
except ModuleNotFoundError as error:
    if error.name not in {"app.mcp.client", "app.mcp.result"}:
        raise
    discover_tools = invoke_tool = tool_contract_hash = normalize_mcp_result = None
    MCPConnectionError = RuntimeError

SCHEMA = {"type": "object", "properties": {"database": {"type": "string"}},
          "required": ["database"], "additionalProperties": False}


def feature():
    assert discover_tools is not None, "MCP 通信尚未实现"


def server_config(tmp_path, timeout=5):
    digest = tool_contract_hash(SCHEMA, None)
    return MCPConfig.model_validate_json(json.dumps({"servers": [{
        "id": "dbdiag", "command": sys.executable, "args": [], "cwd": str(tmp_path),
        "timeout_seconds": timeout, "tools": [{"remote_name": "get_connections",
        "local_name": "mcp_dbdiag_get_connections", "description": "查询",
        "risk_level": "low", "expected_contract_sha256": digest,
        "allowed_arguments": {"database": ["shop"]}}]}]})).servers[0]


def descriptor(name="get_connections", schema=None):
    return SimpleNamespace(name=name, input_schema=schema or SCHEMA, output_schema=None,
                           annotations=None)


class FakeClient:
    def __init__(self, pages=None, result=None, delay=0):
        self.pages = pages or [SimpleNamespace(tools=[descriptor()], next_cursor=None)]
        self.result = result or SimpleNamespace(is_error=False, structured_content={"active": 180}, content=[])
        self.delay = delay
        self.cursors, self.calls, self.closed = [], [], False

    async def __aenter__(self): return self
    async def __aexit__(self, *_): self.closed = True
    async def list_tools(self, cursor=None):
        self.cursors.append(cursor)
        return self.pages[min(len(self.cursors) - 1, len(self.pages) - 1)]
    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        await asyncio.sleep(self.delay)
        return self.result


def test_discovery_follows_pages_and_closes(tmp_path):
    feature()
    fake = FakeClient(pages=[SimpleNamespace(tools=[descriptor()], next_cursor="next"),
                             SimpleNamespace(tools=[descriptor("other")], next_cursor=None)])
    tools = asyncio.run(discover_tools(server_config(tmp_path), client_factory=lambda _: fake))
    assert [tool.name for tool in tools] == ["get_connections", "other"]
    assert fake.cursors == [None, "next"] and fake.closed


def test_repeated_cursor_and_external_schema_reference_are_rejected(tmp_path):
    feature()
    for fake in [FakeClient(pages=[SimpleNamespace(tools=[], next_cursor="same")]),
                 FakeClient(pages=[SimpleNamespace(tools=[descriptor(schema={
                     "type": "object", "$ref": "https://untrusted.invalid/schema"})], next_cursor=None)])]:
        with pytest.raises(MCPConnectionError):
            asyncio.run(discover_tools(server_config(tmp_path), client_factory=lambda _: fake))
        assert fake.closed


def test_invocation_rechecks_contract_before_any_remote_call(tmp_path):
    feature()
    config = server_config(tmp_path)
    observed = asyncio.run(discover_tools(config, client_factory=lambda _: FakeClient()))[0]
    changed = FakeClient(pages=[SimpleNamespace(tools=[descriptor(schema={
        "type": "object", "properties": {"command": {"type": "string"}}})], next_cursor=None)])
    result = asyncio.run(invoke_tool(config, config.tools[0], observed, {"database": "shop"},
                                     client_factory=lambda _: changed))
    assert result.status == "error" and changed.calls == [] and changed.closed


def test_success_and_timeout_close_their_client(tmp_path):
    feature()
    config = server_config(tmp_path, timeout=0.05)
    observed = asyncio.run(discover_tools(config, client_factory=lambda _: FakeClient()))[0]
    for fake, expected in [(FakeClient(), "success"), (FakeClient(delay=0.2), "error")]:
        result = asyncio.run(invoke_tool(config, config.tools[0], observed, {"database": "shop"},
                                         client_factory=lambda _: fake))
        assert result.status == expected and fake.closed
        if expected == "success":
            assert result.data["source"]["server_id"] == "dbdiag"
            assert result.data["payload"]["active"] == 180


@pytest.mark.parametrize("body,expected", [({"status": "no_data"}, "no_data"),
    ({"state": "failed"}, "success"), ({"active": 180}, "success"), ([], "no_data")])
def test_normalizer_keeps_query_and_service_states_distinct(body, expected):
    feature()
    raw = SimpleNamespace(is_error=False, structured_content=body, content=[])
    result = normalize_mcp_result(raw, server_id="db", remote_name="query")
    assert result.status == expected
    assert result.data["source"]["transport"] == "mcp"


def test_error_and_media_output_are_not_successful_observations():
    feature()
    for raw in [SimpleNamespace(is_error=True, structured_content=None,
                 content=[SimpleNamespace(type="text", text="API_KEY=secret-sentinel")]),
                SimpleNamespace(is_error=False, structured_content=None,
                 content=[SimpleNamespace(type="image", data="not-decoded")])]:
        result = normalize_mcp_result(raw, server_id="db", remote_name="query")
        assert result.status == "error"
        assert "secret-sentinel" not in json.dumps(result.to_dict())


def test_credentials_are_redacted_and_large_output_is_marked():
    feature()
    raw = SimpleNamespace(is_error=False, structured_content={"password":"dictionary-secret",
        "message":"Authorization: Bearer bearer-secret API_KEY=assigned-secret private-value",
        "payload":"x" * 5000}, content=[])
    result = normalize_mcp_result(raw, server_id="db", remote_name="query", max_chars=600,
                                  secret_values=("private-value",))
    text = json.dumps(result.to_dict())
    for secret in ["dictionary-secret", "bearer-secret", "assigned-secret", "private-value"]:
        assert secret not in text
    assert result.data["payload"]["_truncated"] is True


def test_transport_error_does_not_echo_exception_text(tmp_path):
    feature()
    class FailingClient(FakeClient):
        async def __aenter__(self): raise RuntimeError("transport-secret-sentinel")
    with pytest.raises(MCPConnectionError) as caught:
        asyncio.run(discover_tools(server_config(tmp_path), client_factory=lambda _: FailingClient()))
    assert "transport-secret-sentinel" not in str(caught.value)


@pytest.mark.parametrize("schema", [
    {"type":"object","properties":{"connection":{"type":"object","properties":{"password":{"type":"string"}}}}},
    {"type":"object","properties":{"targets":{"type":"array","items":{"type":"object","properties":{"api_key":{"type":"string"}}}}}},
])
def test_nested_credential_parameters_are_rejected_before_registration(tmp_path, schema):
    fake = FakeClient(pages=[SimpleNamespace(tools=[descriptor(schema=schema)], next_cursor=None)])
    with pytest.raises(MCPConnectionError):
        asyncio.run(discover_tools(server_config(tmp_path), client_factory=lambda _: fake))
    assert fake.closed


def test_near_limit_result_preserves_source_through_executor(executor):
    raw = SimpleNamespace(is_error=False, structured_content={"message":"x" * 7972}, content=[])
    result = normalize_mcp_result(raw, server_id="dbdiag", remote_name="get_connections")
    truncated = executor._truncate(result)
    assert truncated.data["source"]["transport"] == "mcp"
    assert len(json.dumps(truncated.data, ensure_ascii=False)) <= 8000



def test_sdk_parse_exception_logs_never_include_protocol_input(caplog):
    from mcp.client.stdio import _parse_line
    from app.mcp.logging import safe_sdk_logs
    import logging
    previous = logging.getLogRecordFactory()
    with caplog.at_level(logging.ERROR), safe_sdk_logs():
        error = _parse_line("stdout-secret-sentinel")
        assert isinstance(error,Exception)
        logging.getLogger("mcp.new_logger").error("payload %s", "stdout-secret-sentinel")
        with safe_sdk_logs():
            logging.getLogger("app.test").error("ordinary app message")
    assert "stdout-secret-sentinel" not in caplog.text
    assert "ordinary app message" in caplog.text
    assert logging.getLogRecordFactory() is previous



def test_sdk_notification_validation_log_is_hidden(caplog):
    from app.mcp.logging import safe_sdk_logs
    from mcp.client.session import ClientSession
    session=object.__new__(ClientSession)
    session._negotiated_version=None
    session._notification_bindings={}
    async def notify():
        await session._on_notify(None,"notifications/progress",{
            "progressToken":"fixture","progress":"notification-secret-sentinel"})
    with safe_sdk_logs(): asyncio.run(notify())
    assert "notification-secret-sentinel" not in caplog.text


def test_sdk_logging_factory_can_be_wrapped_between_scopes(caplog):
    from app.mcp.logging import safe_sdk_logs
    import logging
    original=logging.getLogRecordFactory()
    try:
        with safe_sdk_logs():
            captured=logging.getLogRecordFactory()
            def external_factory(*args,**kwargs): return captured(*args,**kwargs)
            logging.setLogRecordFactory(external_factory)
        with safe_sdk_logs():
            logging.getLogger("app.test").error("ordinary message")
            logging.getLogger("mcp.test").error("factory-secret-sentinel")
        assert "ordinary message" in caplog.text
        assert "factory-secret-sentinel" not in caplog.text
    finally:
        logging.setLogRecordFactory(original)
