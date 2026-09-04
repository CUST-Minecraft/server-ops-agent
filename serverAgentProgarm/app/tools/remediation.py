"""修复类工具（写操作）。每个工具必须标注 risk_level，并接受最严格的参数校验。"""
from app.ssh.ssh_client import SSHClient
from app.tools.base import Tool
from app.tools.builtin import validate_service_name


def build_remediation_tools(ssh: SSHClient) -> list[Tool]:
    def restart_service(args: dict) -> dict:
        service = validate_service_name(args["service"])      # 复用 Day 2 的白名单校验
        r = ssh.run(f"sudo -n systemctl restart {service}")
        if r["exit_code"] != 0:
            raise RuntimeError(f"restart {service} 失败(exit={r['exit_code']}): {r['stderr']}")
        return {"service": service, "restarted": True, "elapsed_ms": r["elapsed"]}

    return [
        Tool(
            name="restart_service",
            description="重启指定的 systemd 服务。这是写操作，会中断服务，仅用于故障修复。",
            parameters={"type": "object",
                        "properties": {"service": {"type": "string",
                                                     "description": "服务名，如 nginx、mysql"}},
                        "required": ["service"]},
            handler=restart_service,
            risk_level="medium",          # 默认中等；关键服务由权限引擎动态升级为 high
        ),
    ]

if __name__ == "__main__":
    tools = build_remediation_tools(ssh=SSHClient())
    handler = tools[0].handler({"service": "docker"})
    print(handler)
