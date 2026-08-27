"""修复预案库。LLM 只能从这里选择并填参（Day 9），不能发明库外动作。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Runbook:
    name: str                 # 唯一标识（LLM 的选择题答案只能是它）
    description: str          # 给人看的说明
    trigger: str              # 给 LLM 看的适用场景描述（Day 9 匹配用）
    plan: dict                # {"tool": ..., "args": {...}}（参数可含占位符）
    postcondition: dict       # 步骤 1 的形状
    risk_note: str            # 风险备注（审批人参考）


RUNBOOKS: list[Runbook] = [
    Runbook(
        name="nginx_restart",
        description="重启 nginx 服务",
        trigger="适用于 nginx 服务异常/inactive、或 80 端口不通的场景",
        plan={"tool": "restart_service", "args": {"service": "nginx"}},
        postcondition={"checks": [
            {"tool": "get_service_status", "args": {"service": "nginx"},
             "expect": {"active": True}},
            {"tool": "tcp_probe", "args": {"port": 80}, "expect": {"port_open": True}},
        ]},
        risk_note="重启期间 nginx 短暂不可用（秒级）",
    ),
    Runbook(
        name="docker_restart",
        description="重启 docker 服务（MySQL 容器随之重启）",
        trigger="适用于 docker 服务异常导致容器（含 MySQL）不工作的场景",
        plan={"tool": "restart_service", "args": {"service": "docker"}},
        postcondition={"checks": [
            {"tool": "get_service_status", "args": {"service": "docker"},
             "expect": {"active": True}},
            {"tool": "tcp_probe", "args": {"port": 3306}, "expect": {"port_open": True}},
        ]},
        risk_note="所有容器重启，MySQL 短暂不可用（约 10-30 秒）",
    ),
]