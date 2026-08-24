"""Day 6 演示：权限引擎决策矩阵。"""
from app.security.policy import PermissionEngine
from app.tools.base import Tool
from app.tools.remediation import build_remediation_tools
from app.ssh.ssh_client import SSHClient

restart = build_remediation_tools(SSHClient())[0]
cpu = Tool(name="get_cpu_status", description="x",
           parameters={"type": "object", "properties": {}}, handler=lambda a: {})

CASES = [
    ("get_cpu_status()", cpu, {}),
    ("restart_service(nginx)", restart, {"service": "nginx"}),
    ("restart_service(mysql)", restart, {"service": "mysql"}),
    ('restart_service("nginx; shutdown")', restart, {"service": "nginx; shutdown -h now"}),
]

for mode in ("standard", "auto", "strict"):
    print(f"\n== mode={mode} ==")
    engine = PermissionEngine(mode)
    for label, tool, args in CASES:
        d = engine.check(tool, args)
        print(f"  {label:38s} -> {d.decision.value:16s} ({d.reason})")