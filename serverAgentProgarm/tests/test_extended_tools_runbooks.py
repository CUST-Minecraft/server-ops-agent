from app.remediation.runbooks import get_runbooks
from app.tools.builtin import build_readonly_tools


def test_extended_diagnostic_tools_parse_structured_output():
    from tests.conftest import FakeSSHClient

    ssh = FakeSSHClient({
        "systemctl show": (
            "ActiveState=active\nSubState=running\nMainPID=123\n"
            "ExecMainStartTimestamp=Tue 2026-09-09 01:00:00 UTC\n"
            "FragmentPath=/usr/lib/systemd/system/nginx.service\n"
        ),
        "ps -eo": "PID COMMAND %CPU %MEM RSS\n123 nginx 10.0 2.0 12345\n",
        "ss -lntH": "LISTEN 0 128 0.0.0.0:80 0.0.0.0:*\n",
    })
    tools = {tool.name: tool for tool in build_readonly_tools(ssh)}

    details = tools["get_service_details"].handler({"service": "nginx"})
    processes = tools["get_top_processes"].handler({})
    ports = tools["get_listening_ports"].handler({})

    assert details["active_state"] == "active"
    assert details["main_pid"] == 123
    assert processes["processes"][0]["command"] == "nginx"
    assert ports["ports"][0]["port"] == 80


def test_configured_service_ports_create_safe_runbooks(monkeypatch):
    monkeypatch.setenv("RECOVERY_SERVICE_PORTS", "mysql:3306,redis:6379")

    runbooks = get_runbooks()
    names = {runbook.name for runbook in runbooks}

    assert "mysql_restart" in names
    assert "redis_restart" in names
    mysql = next(runbook for runbook in runbooks if runbook.name == "mysql_restart")
    check_args = [check["args"] for check in mysql.postcondition["checks"]]
    assert {"service": "mysql"} in check_args
    assert {"port": 3306} in check_args
