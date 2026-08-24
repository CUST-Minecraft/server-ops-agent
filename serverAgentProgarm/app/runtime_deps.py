"""跨入口共享的装配函数（Day 10 的 CLI 也用它）。"""
from app.agent.executor import ToolExecutor
from app.config import ServerSettings
from app.llm.llm_client import LLMClient
from app.security.approval import ApprovalManager
from app.security.policy import PermissionEngine
from app.ssh.ssh_client import SSHClient
from app.storage.db import SessionLocal
from app.tools.builtin import build_readonly_tools
from app.tools.remediation import build_remediation_tools
from app.tools.registry import ToolRegistry


def build_executor_and_approvals() -> tuple:
    settings = ServerSettings()
    ssh = SSHClient()
    registry = ToolRegistry()
    for tool in build_readonly_tools(ssh) + build_remediation_tools(ssh):
        registry.register(tool)
    policy = PermissionEngine(settings.policy_mode)
    executor = ToolExecutor(registry, policy=policy, session_factory=SessionLocal)
    approvals = ApprovalManager(SessionLocal, executor,
                                 ttl_minutes=settings.approval_ttl_minutes)
    executor.approval_manager = approvals
    return executor, registry, approvals