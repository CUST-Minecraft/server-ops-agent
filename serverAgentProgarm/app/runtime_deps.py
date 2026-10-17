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


def build_executor_and_approvals(*, include_mcp: bool = False) -> tuple[ToolExecutor, ToolRegistry, ApprovalManager]:
    settings = ServerSettings()
    ssh = SSHClient()
    registry = ToolRegistry()
    for tool in build_readonly_tools(ssh) + build_remediation_tools(ssh):
        registry.register(tool)
    if settings.recovery_rag_enabled:
        from app.knowledge.embeddings import build_embedding_provider
        from app.knowledge.retriever import RecoveryIndex
        from app.tools.knowledge import build_knowledge_tools

        recovery_index = RecoveryIndex(
            settings.recovery_index_path,
            build_embedding_provider(settings),
            dense_min_score=settings.recovery_dense_min_score,
            candidate_limit=settings.recovery_candidate_limit,
            rrf_k=settings.recovery_rrf_k,
        )
        for tool in build_knowledge_tools(
            recovery_index,
            top_k=settings.recovery_top_k,
            max_context_chars=settings.recovery_context_max_chars,
        ):
            registry.register(tool)
    if include_mcp and settings.mcp_enabled:
        from app.tools.mcp import register_mcp_tools
        register_mcp_tools(registry, settings)
    policy = PermissionEngine(settings.policy_mode)
    executor = ToolExecutor(registry, policy=policy, session_factory=SessionLocal)
    approvals = ApprovalManager(SessionLocal, executor,
                                 ttl_minutes=settings.approval_ttl_minutes)
    executor.approval_manager = approvals
    return executor, registry, approvals
