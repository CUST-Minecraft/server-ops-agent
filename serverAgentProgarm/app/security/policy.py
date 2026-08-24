"""权限引擎：四层闸门，确定性决策。所有写操作的安全边界在这里，不在 Prompt。"""
from dataclasses import dataclass
from enum import Enum

from app.tools.base import Tool


class RiskLevel(str, Enum):
    LOW = "low"; MEDIUM = "medium"; HIGH = "high"


class Decision(str, Enum):
    ALLOW = "allow"; NEEDS_APPROVAL = "needs_approval"; DENY = "deny"


@dataclass(frozen=True)
class PermissionDecision:
    decision: Decision
    reason: str


# 关键服务：重启它们可能让系统失能（重启 sshd = 把自己锁在门外）
CRITICAL_SERVICES = {"mysql", "mysqld", "ssh", "sshd", "docker", "systemd", "networkd"}

# 黑名单模式：无论谁、以何种理由，出现即拒绝（纵深防御：正常参数校验应早已拦截）
DENY_PATTERNS = ["rm -rf", "mkfs", "dd if=", "shutdown", "reboot", "halt",
                 ":(){", "fork bomb", "> /dev/sd", "chmod -R 777 /"]


class PermissionEngine:
    def __init__(self, mode: str = "standard"):
        if mode not in ("standard", "strict", "auto"):
            raise ValueError(f"未知权限模式: {mode}")
        self.mode = mode

    def check(self, tool: Tool, args: dict) -> PermissionDecision:
        # ---- 闸门1：黑名单模式（拒绝优先） ----
        for value in args.values():
            if isinstance(value, str):
                lowered = value.lower()
                for pattern in DENY_PATTERNS:
                    if pattern in lowered:
                        return PermissionDecision(
                            Decision.DENY, f"参数命中黑名单模式: {pattern!r}")

        # ---- 闸门2：静态风险 ----
        try:
            risk = RiskLevel(tool.risk_level)
        except ValueError:
            return PermissionDecision(Decision.DENY,
                                      f"工具声明了未知风险等级: {tool.risk_level!r}")

        #   若 tool.name == "restart_service" 且 str(args.get("service", "")).lower()
        #   在 CRITICAL_SERVICES 中 -> risk = RiskLevel.HIGH
        #   （提示：先 .lower() 再匹配；这一层是"静态基线上的修正"）

        if tool.name == "restart_service":
            lower = str(args.get("service", "")).lower()
            if lower in CRITICAL_SERVICES:
                risk = RiskLevel.HIGH
        # ---- 闸门4：模式策略 ----
        return self._decide(risk)

    def _decide(self, risk: RiskLevel) -> PermissionDecision:
        #   low                                 -> ALLOW，reason "只读操作"
        #   mode == "auto" 且 risk == MEDIUM    -> ALLOW，reason "auto 模式：中风险自动放行"
        #   其余（medium/high，任意模式）        -> NEEDS_APPROVAL，
        #       reason f"{risk.value} 级写操作（mode={self.mode}），需人工审批"
        if risk == RiskLevel.LOW:
            return PermissionDecision(Decision.ALLOW,"低风险只读操作")
        elif risk == RiskLevel.MEDIUM and self.mode == "auto":
            return PermissionDecision(Decision.ALLOW,f"{self.mode}模式,中风险,自动操作模式")
        else:
            return PermissionDecision(Decision.NEEDS_APPROVAL,f"{risk.value} 级写操作（mode={self.mode}），需人工审批")
