"""审计写入。executor 每次权限决策后调用。"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import sessionmaker

from app.security.policy import PermissionDecision

logger = logging.getLogger(__name__)


def log_decision(session_factory: sessionmaker, tool: str, args: dict,
                 decision: PermissionDecision, incident_id: int | None = None) -> None:
    from app.storage.models import AuditLog
    try:
        with session_factory() as session:
            session.add(AuditLog(
                ts=datetime.now(timezone.utc), tool=tool, args=args,
                decision=decision.decision.value, reason=decision.reason,
                incident_id=incident_id))
            session.commit()
        logger.info("AUDIT tool=%s decision=%s reason=%s", tool, decision.decision.value,
                    decision.reason)
    except Exception:                    # noqa: BLE001  审计失败不许影响主流程
        logger.exception("审计写入失败（不影响工具执行）")