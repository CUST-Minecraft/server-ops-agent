"""工具执行器：执行的唯一入口。Day 6 起在这里插入权限检查与审计。"""
import logging
import time
from app.security.audit import log_decision
from app.security.policy import Decision
from app.tools.base import ToolResult
from app.tools.registry import ToolRegistry
from app.security.policy import PermissionEngine

logger = logging.getLogger(__name__)

class ToolExecutor:
    def __init__(self,registry: ToolRegistry,policy: PermissionEngine | None = None, session_factory=None, approval_manager=None):
        self.session_factory = session_factory
        self.policy = policy
        self.registry = registry
        self.approval_manager = approval_manager
        if policy is not None and approval_manager is None:
            logger.warning("权限引擎已启用但审批管理器未装配："
                           "NEEDS_APPROVAL 将无法创建审批单")

    def execute(self, name: str, args: dict | None = None,approved: bool = False) -> ToolResult:
        """执行一个工具。约定：本方法永不抛异常，失败也以 ToolResult(status=error) 返回。"""
        args = args or {}
        invocation = f"{name}({', '.join(f'{k}={v!r}' for k, v in args.items())})"
        tool = self.registry.get(name)
        if tool is None:                                    # 情况一已给：未知工具
            return ToolResult(status="error", error=f"未知工具: {name}",
                              invocation=invocation)

        start = time.monotonic()

        # ---- 权限闸门（Day 6）：所有工具必经 ----
        if self.policy is not None:
            decision = self.policy.check(tool, args)
            if self.session_factory is not None:
                log_decision(self.session_factory, name, args, decision)
            if decision.decision == Decision.DENY:
                return ToolResult(status="error",
                                  error=f"权限拒绝: {decision.reason}", invocation=invocation)
            #   返回 ToolResult(status="approval_required",
            #                   error=f"等待人工审批: {decision.reason}", invocation=...)
            #   （不是 error！--它表达"操作合法但被挂起"，Day 7 起会在此创建审批单）

            needs = decision.decision == Decision.NEEDS_APPROVAL
            if needs and not approved:
                if self.approval_manager is not None:
                    req = self.approval_manager.create_pending(name, args, decision.reason)
                    return ToolResult(
                        status="approval_required",
                        error=f"已创建审批单 #{req.id}"
                              f"（{self.approval_manager.ttl_minutes}分钟内有效），等待人工批准",
                        invocation=invocation,
                    )
                # 装配缺陷：策略能挂起，却没有解除挂起的组件
                logger.error("工具 %s 需要审批，但 approval_manager 未装配，挂起无法解除", name)
                return ToolResult(
                    status="error",
                    error="审批管理器未装配，无法创建审批单（配置错误）",
                    invocation=invocation,
                )
            if needs and approved:
                logger.info("工具 %s 凭已批准的审批单执行", name)


        # ---- 闸门通过，执行（与 Day 3 相同） ----



        try:
            result = tool.handler(args)
            elapsed = int((time.monotonic() - start) * 1000)
            #   - result 已是 ToolResult：补默认的 invocation/elapsed_ms（若为空/0）后返回
            #   - result 是普通 dict：包装成 ToolResult(status="success", data=result, ...)

            if isinstance(result, ToolResult):
                result.invocation = result.invocation or invocation
                result.elapsed_ms = elapsed
                return result
            if isinstance(result, dict):
                return ToolResult(
                    status="success",
                    data=result,
                    invocation=invocation,
                    elapsed_ms=elapsed
                )
            return ToolResult(status="error",
                              error=f"工具返回了无法识别的类型: {type(result).__name__}",
                              invocation=invocation, elapsed_ms=elapsed)

        except Exception as e:  # noqa: BLE001  执行器必须兜住一切
            elapsed = int((time.monotonic() - start) * 1000)
            #   返回 ToolResult(status="error", error=f"{type(e).__name__}: {e}",
            #                   invocation=..., elapsed_ms=...)
            return ToolResult(
                status="error",
                error=f"{type(e).__name__}: {e}",
                invocation=invocation,
                elapsed_ms=elapsed
            )