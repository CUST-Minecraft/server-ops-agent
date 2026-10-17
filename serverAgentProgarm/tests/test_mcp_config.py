"""MCP 配置的强边界；新功能不存在时明确失败。"""
import json
from pathlib import Path
import sys
import pytest

try:
    from app.mcp.config import MCPConfigError, load_mcp_config
except ModuleNotFoundError as error:
    if error.name not in {"app.mcp", "app.mcp.config"}:
        raise
    MCPConfigError = ValueError
    load_mcp_config = None


def config_payload(tmp_path):
    return {"servers": [{"id": "dbdiag", "command": sys.executable,
        "args": ["-u", "fixture.py"], "cwd": str(tmp_path), "env_vars": [],
        "timeout_seconds": 5, "tools": [{"remote_name": "get_connections",
        "local_name": "mcp_dbdiag_get_connections", "description": "查询已授权数据库",
        "risk_level": "low", "allowed_arguments": {"database": ["shop"]},
        "expected_contract_sha256": "a" * 64}]}]}


def write_config(tmp_path, payload):
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def loader():
    assert load_mcp_config is not None, "MCP 配置加载尚未实现"
    return load_mcp_config


def test_valid_config_keeps_local_policy_and_environment_names(tmp_path):
    config = loader()(write_config(tmp_path, config_payload(tmp_path)))
    server = config.servers[0]
    assert server.id == "dbdiag" and server.timeout_seconds == 5
    assert server.tools[0].allowed_arguments["database"] == ("shop",)
    assert server.env_vars == ()


@pytest.mark.parametrize("change", ["relative_command", "missing_command", "relative_cwd",
    "unknown_risk", "missing_risk", "duplicate_server", "duplicate_alias", "invalid_alias",
    "short_hash", "unknown_field", "empty_scope", "unsupported_transport"])
def test_invalid_config_is_rejected_before_any_server_starts(tmp_path, change):
    payload = config_payload(tmp_path)
    server, tool = payload["servers"][0], payload["servers"][0]["tools"][0]
    if change == "relative_command": server["command"] = "python"
    elif change == "missing_command": server["command"] = str(tmp_path / "missing.exe")
    elif change == "relative_cwd": server["cwd"] = "."
    elif change == "unknown_risk": tool["risk_level"] = "high"
    elif change == "missing_risk": del tool["risk_level"]
    elif change == "duplicate_server": payload["servers"].append(server.copy())
    elif change == "duplicate_alias": server["tools"].append(tool.copy())
    elif change == "invalid_alias": tool["local_name"] = "../get-data"
    elif change == "short_hash": tool["expected_contract_sha256"] = "abc"
    elif change == "unknown_field": server["env"] = {"API_KEY": "not-allowed-plaintext"}
    elif change == "empty_scope": tool["allowed_arguments"] = {"database": []}
    elif change == "unsupported_transport": server["transport"] = "http"
    with pytest.raises(MCPConfigError):
        loader()(write_config(tmp_path, payload))


def test_validation_error_does_not_echo_configuration_secrets(tmp_path):
    payload = config_payload(tmp_path)
    payload["servers"][0]["env"] = {"API_KEY": "configuration-secret-sentinel"}
    with pytest.raises(MCPConfigError) as caught:
        loader()(write_config(tmp_path, payload))
    assert "configuration-secret-sentinel" not in str(caught.value)


def test_malformed_or_missing_json_has_fixed_error(tmp_path):
    load = loader()
    with pytest.raises(MCPConfigError): load(tmp_path / "missing.json")
    path = tmp_path / "bad.json"
    path.write_text('{"API_KEY":"secret-sentinel",', encoding="utf-8")
    with pytest.raises(MCPConfigError) as caught: load(path)
    assert "secret-sentinel" not in str(caught.value)
