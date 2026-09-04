import pytest

from app.security.policy import Decision, PermissionEngine
from app.tools.base import Tool


RESTART = Tool(
    name="restart_service",
    description="restart",
    parameters={"type": "object", "properties": {}},
    handler=lambda _args: {},
    risk_level="medium",
)
CPU = Tool(
    name="get_cpu_status",
    description="read",
    parameters={"type": "object", "properties": {}},
    handler=lambda _args: {},
)

CASES = [
    ("standard", CPU, {}, Decision.ALLOW),
    ("auto", CPU, {}, Decision.ALLOW),
    ("strict", CPU, {}, Decision.ALLOW),
    ("standard", RESTART, {"service": "nginx"}, Decision.NEEDS_APPROVAL),
    ("auto", RESTART, {"service": "nginx"}, Decision.ALLOW),
    ("strict", RESTART, {"service": "nginx"}, Decision.NEEDS_APPROVAL),
    ("standard", RESTART, {"service": "mysql"}, Decision.NEEDS_APPROVAL),
    ("auto", RESTART, {"service": "mysql"}, Decision.NEEDS_APPROVAL),
    ("strict", RESTART, {"service": "mysql"}, Decision.NEEDS_APPROVAL),
    ("standard", RESTART, {"service": "nginx; shutdown"}, Decision.DENY),
    ("auto", RESTART, {"service": "nginx; reboot"}, Decision.DENY),
    ("strict", RESTART, {"service": "x; rm -rf /"}, Decision.DENY),
]


@pytest.mark.parametrize("mode,tool,args,expected", CASES)
def test_decision_matrix(mode, tool, args, expected):
    assert PermissionEngine(mode).check(tool, args).decision == expected
