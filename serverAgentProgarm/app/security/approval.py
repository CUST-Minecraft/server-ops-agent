import hashlib, json
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import sessionmaker
from sqlalchemy import CursorResult, update,select
from typing import cast


from app.agent.executor import ToolExecutor
from app.storage.models import ApprovalRequest

def args_hash(args: dict) -> str:
    """参数指纹。sort_keys 保证同内容不同顺序也同哈希。"""
    canonical = json.dumps(args, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()

logger = logging.getLogger(__name__)


class ApprovalManager:
    def __init__(self, session_factory: sessionmaker, executor: ToolExecutor,
                 ttl_minutes: int = 60):
        self.session_factory = session_factory
        self.executor = executor
        self.ttl_minutes = ttl_minutes

    def create_pending(self, tool: str, args: dict, reason: str,
                       incident_id: int | None = None) -> ApprovalRequest:
        """executor 遇到 NEEDS_APPROVAL 时调用。"""
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            req = ApprovalRequest(
                tool=tool, args=args, args_hash=args_hash(args), reason=reason,
                status="pending", incident_id=incident_id,
                created_at=now, expires_at=now + timedelta(minutes=self.ttl_minutes))
            session.add(req)
            session.commit()
            logger.warning("审批单 #%s 已创建: %s(%s) 理由: %s", req.id, tool, args, reason)
            return req

    def list_pending(self) -> list[ApprovalRequest]:
        with self.session_factory() as session:
            stmt = (select(ApprovalRequest)
                    .where(ApprovalRequest.status == "pending")
                    .order_by(ApprovalRequest.id))  # 补这个
            return list(session.scalars(stmt).all())

    def approve(self, approval_id: int, actor: str = "operator") -> str:
        #   1) 查单；不存在 -> 返回错误信息
        #   2) 状态必须是 pending，否则报"已处理/已过期"
        #   3) 未过期：now < expires_at；过期 -> 把状态改为 expired 并返回提示
        #   4) 哈希校验：args_hash(req.args) == req.args_hash，不符 -> 拒绝执行（篡改警报）
        #   5) 执行：result = self.executor.execute(req.tool, req.args, approved=True)
        #      然后更新单据：status="approved", decided_at/decided_by/result_status=result.status
        #      返回执行结果摘要
        with self.session_factory() as session:
            approval = session.scalars(
                select(ApprovalRequest).where(ApprovalRequest.id == approval_id)
            ).first()
            if approval is None:
                return f"没有查询到该id{approval_id}审批单"
            if approval.status != "pending":
                return f"{approval.id}审批单已过期/已处理"

            expires = approval.expires_at
            if expires.tzinfo is None:  # SQLite 读回丢了时区 -> 补回
                expires = expires.replace(tzinfo=timezone.utc)

            if datetime.now(timezone.utc) > expires:
                approval.status = "expired" # 已经过期
                approval.decided_at = datetime.now(timezone.utc)
                session.commit()
                return f"该审批单{approval.id}已经过期"
            if args_hash(approval.args) != approval.args_hash:
                logger.warning(f"该审批单{approval.id}参数被篡改")
                return f"参数被篡改,无法处理"
            result = self.executor.execute(approval.tool, approval.args, approved=True)
            approval.status = "approved"
            approval.decided_at = datetime.now(timezone.utc)
            approval.decided_by = actor
            approval.result_status = result.status
            session.commit()


            if result.status == "error":
                logger.warning(f"处理失败:错误输出:{result.error},执行内容:{result.invocation}")
                return f"{approval.id}处理失败,原因:{result.error}"
            logger.warning(f"审批单更新{approval.id}更新为approved")
            return f"处理结束,处理结果{result.data},处理内容:{result.invocation}"

    def reject(self, approval_id: int, actor: str = "operator") -> str:
        # TODO(你来实现)：pending -> rejected，记录 decided_at/by；返回摘要
        with self.session_factory() as session:
            approval = session.scalars(select(ApprovalRequest).where(ApprovalRequest.id == approval_id)).first()

            if approval is None:
                return f"没有查询到该id{approval_id}审批单"
            if approval.status != "pending":
                return f"{approval.id}审批单已过期/已处理"
            session.execute(
                update(ApprovalRequest)
                .where(ApprovalRequest.id == approval_id)
                .values(status="rejected",
                        decided_at=datetime.now(timezone.utc),
                        decided_by=actor,
                        )
            )
            session.commit()
            logger.warning(f"拒绝{approval.id},{approval.tool}")
            return f"拒绝{approval.id},{approval.result_status}"


    def expire_stale(self) -> int:
        """把已过期的 pending 单标记为 expired。Runner 每 tick 调用（Day 9）。"""
        # TODO(你来实现)：update ... where status=="pending" and expires_at < now；返回条数
        with self.session_factory() as session:
            now = datetime.now(timezone.utc)
            result = cast(CursorResult,
                session.execute(
                    update(ApprovalRequest)
                    .where(
                        ApprovalRequest.status == "pending",
                        ApprovalRequest.expires_at < now,
                    )
                    .values(status="expired", decided_at=now)
                )
            )

            session.commit()
            return result.rowcount # type: ignore[attr-defined]



if __name__ == '__main__':
    print(args_hash({"a":1, "b":2, "c":3}) == args_hash({"a":1, "b":2, "c":3}))