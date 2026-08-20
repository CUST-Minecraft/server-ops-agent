"""内置只读诊断工具。全部通过注入的 SSHClient 执行，全部只读（不改变服务器状态）。"""
import re
from app.ssh.ssh_client import SSHClient
from app.ssh.ssh_response import SshResponse
from app.tools.base import Tool, ToolResult

# 见步骤 6：服务名的白名单字符集
_SERVICE_NAME_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")
_PATH_RE = re.compile(r"^/[a-zA-Z0-9_./-]*$")


def _run(ssh: SSHClient, cmd: str) -> SshResponse:
    r = ssh.run(cmd)
    if r["exit_code"] != 0:
        raise ValueError(f"命令失败({r['exit_code']}): {cmd} stderr={r['stderr']!r}")
    return r


def build_readonly_tools(ssh: SSHClient) -> list[Tool]:
    def cpu_status(args: dict) -> dict:
        r = _run(ssh, "top -bn1 | grep 'Cpu(s)' ; uptime")
        cpu_line, load_line = r["stdout"].split("\n", 1)
        idle = float(re.search(r"([\d.]+)\s*id", cpu_line).group(1))
        loads = [float(x) for x in re.search(r"load average: ([\d., ]+)", load_line).group(1).split(",")]
        return {"cpu_used_pct": round(100 - idle, 1),
                "load_1m": loads[0], "load_5m": loads[1], "load_15m": loads[2]}

    def memory_usage(args: dict) -> dict:
        r = _run(ssh, "free -m")
        cols = next(l for l in r["stdout"].splitlines() if l.startswith("Mem:")).split()
        total, used, available = int(cols[1]), int(cols[2]), int(cols[6])
        return {"total_mb": total, "used_mb": used, "available_mb": available,
                "used_pct": round((total - available) / total * 100, 1)}

    def disk_usage(args: dict) -> dict:
        path = args.get("path", "/")
        if not _PATH_RE.match(path) or ".." in path:
            raise ValueError(f"非法路径: {path!r}")
        r = _run(ssh, f"df -h {path} | tail -1")
        fs, size, used, avail, use_pct, mounted = r["stdout"].split()
        return {"filesystem": fs, "mount": mounted, "total": size,
                "used": used, "avail": avail, "used_pct": int(use_pct.rstrip("%"))}

    def service_status(args: dict) -> dict:
        service = validate_service_name(args["service"])
        r = ssh.run(f"systemctl is-active {service}")   # 注意：is-active 失败不抛错，状态就在 stdout
        state = r["stdout"].strip() or "unknown"
        return {"service": service, "state": state, "active": state == "active"}

    def read_service_logs(args: dict) -> ToolResult:
        service = validate_service_name(args["service"])
        lines = min(max(int(args.get("lines", 50)), 1), 200)
        r = ssh.run(f"journalctl -u {service} -n {lines} --no-pager")
        logs = r["stdout"].splitlines()
        if not logs or '-- No entries --' in logs:
            return ToolResult(status="no_data", data={"service": service, "count": 0},
                              invocation=f"read_service_logs(service={service})")
        return ToolResult(status="success", data={"service": service, "count": len(logs), "logs": logs},
                          invocation=f"read_service_logs(service={service})")

    return [
        Tool(name="get_cpu_status",
             description="获取目标服务器当前 CPU 使用率（%）与 1/5/15 分钟平均负载",
             parameters={"type": "object", "properties": {}},
             handler=cpu_status),
        Tool(name="get_memory_usage",
             description="获取内存水位：总量/已用/可用（MB）与使用率（%）。used_pct 基于 available 计算",
             parameters={"type": "object", "properties": {}},
             handler=memory_usage),
        Tool(name="get_disk_usage",
             description="获取指定挂载路径的磁盘使用情况。默认根路径 /",
             parameters={"type": "object",
                         "properties": {"path": {"type": "string", "description": "挂载路径，默认 /",
                                                  "pattern": "^/"}},
                         "required": []},
             handler=disk_usage),
        Tool(name="get_service_status",
             description="查询 systemd 服务当前状态（active/inactive/failed）",
             parameters={"type": "object",
                         "properties": {"service": {"type": "string",
                                                     "description": "服务名，如 nginx、mysql"}},
                         "required": ["service"]},
             handler=service_status),
        Tool(name="read_service_logs",
             description="读取 systemd 服务最近的日志（journalctl），用于排查服务异常",
             parameters={"type": "object",
                         "properties": {"service": {"type": "string", "description": "服务名"},
                                        "lines": {"type": "integer", "minimum": 1, "maximum": 200,
                                                  "description": "返回行数，默认 50"}},
                         "required": ["service"]},
             handler=read_service_logs),
    ]


def validate_service_name(service: str) -> str:
    if not isinstance(service, str) or not _SERVICE_NAME_RE.match(service):
        raise ValueError(f"非法服务名: {service!r}（只允许字母/数字/._-）")
    return service


if __name__ == "__main__":
    ssh = SSHClient()
    tools = build_readonly_tools(ssh)
    by_name = {t.name: t for t in tools}
    # print(by_name["get_cpu_status"].handler({}))
    # print(by_name["get_service_status"].handler({"service": "ssh"}))
    print(by_name["read_service_logs"].handler({"service": "noservice"}))
    # print(by_name["get_service_status"].handler({"service": "nginx; rm -rf /"}))