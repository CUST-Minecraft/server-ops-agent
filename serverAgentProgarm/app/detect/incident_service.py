"""Incident 开单/关单：唯一会写 incidents 表的地方。"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session, sessionmaker

from app.detect.detector import DetectEvent
from app.storage.models import Incident

logger = logging.getLogger(__name__)


class IncidentService:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def apply(self, events: list[DetectEvent]) -> list[Incident]:
        changed: list[Incident] = []
        with self.session_factory() as session:
            for e in events:
                if e.action == "open":
                    existing = self._find_open(session, e.kind)
                    if existing:                      # 去重：已有 open 单则跳过
                        continue
                    inc = Incident(kind=e.kind, severity=e.severity, status="open",
                                   title=e.title, detail=e.detail,
                                   opened_at=datetime.now(timezone.utc))
                    session.add(inc)
                    session.flush()                   # 拿到自增 id
                    changed.append(inc)
                    logger.warning("Incident #%s 已开启: %s (%s)", inc.id, inc.title, e.detail)
                elif e.action == "resolve":
                    #   1) inc = self._find_open(session, e.kind)；没有 open 单则跳过
                    #   2) inc.status = "resolved"；inc.resolved_at = 当前 UTC 时间
                    #   3) changed.append(inc)
                    #   4) logger.warning("Incident #%s 已解决: %s", inc.id, inc.title)
                    ...
                    inc = self._find_open(session, e.kind)
                    if inc is None:
                        continue
                    inc.status = "resolved"
                    inc.resolved_at = datetime.now(timezone.utc)
                    changed.append(inc)
                    logger.warning("Incident #%s 已解决: %s", inc.id, inc.title)
            session.commit()
        return changed

    @staticmethod
    def _find_open(session: Session, kind: str) -> Incident | None:
        return (session.query(Incident)
                .filter(Incident.kind == kind, Incident.status == "open")
                .order_by(Incident.id.desc()).first())