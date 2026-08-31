"""Incident 开单/关单：唯一会写 incidents 表的地方。"""
import copy
import logging
from datetime import datetime, timezone
from app.alert import Alerter
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from app.detect.detector import DetectEvent
from app.storage.models import Incident

logger = logging.getLogger(__name__)

ALLOWED_TRANSITIONS :  dict[str, set[str]] = {
    "open":              {"investigating", "resolved"},     # 检测器确认恢复可直接关单
    "investigating":     {"awaiting_approval", "open", "failed", "resolved"},  # open=调查无果回退重试; resolved=auto 模式执行预案验证通过直接关单
    "awaiting_approval": {"remediating", "failed", "resolved", "open"},    # rejected/过期 -> failed; 数据不一致(无关联审批单)回退 open 重查
    "remediating":       {"resolved", "failed"},
    "failed":            {"investigating"},                 # 允许人工重新调查
    "resolved":          set(),
}


class IncidentService:
    def __init__(self, session_factory: sessionmaker,alerter : Alerter | None = None):
        self.session_factory = session_factory
        self.alerter = alerter

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
                    if self.alerter: self.alerter.incident_opened(inc)
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
                    if self.alerter: self.alerter.incident_resolved(inc)
                    logger.warning("Incident #%s 已解决: %s", inc.id, inc.title)
            session.commit()
        return changed



    def update_status(self, incident_id: int, new_status: str,
                      note: str = "") -> bool:
        #   1) 查单；new_status 不在 ALLOWED_TRANSITIONS[当前状态] 里 -> 记 warning 并返回 False
        #   2) 合法 -> 更新 status；resolved 时补 resolved_at
        #   3) 调查结论等附加信息写进 detail（note 拼进 detail["notes"] 列表）
        with self.session_factory() as session:
            inc = session.query(Incident).filter(Incident.id == incident_id).one_or_none()
            if inc is None:
                logger.warning("Incident #%s 不存在，无法更新状态", incident_id)
                return False

            allowed = ALLOWED_TRANSITIONS.get(str(inc.status)) or set()
            if new_status not in allowed:
                logger.warning("非法状态转移: #%s %s -> %s", incident_id, inc.status, new_status)
                return False
            inc.status = new_status
            if new_status == "resolved":
                inc.resolved_at = datetime.now(timezone.utc)
            if note:
                detail = copy.deepcopy(inc.detail)
                detail.setdefault("notes", []).append(note)
                inc.detail = detail
            session.commit()
            return True





    @staticmethod
    def _find_open(session: Session, kind: str) -> Incident | None:
        return (session.query(Incident)
                .filter(Incident.kind == kind, Incident.status == "open")
                .order_by(Incident.id.desc()).first())

    def find_open_kind_set(self) -> set[str]:
        with self.session_factory() as session:
            stmt = (
                select(Incident.kind)  # 直接只查kind字段，不用查完整ORM对象，效率更高
                .where(Incident.status == "open")
            )
            # scalars复数，取出每一行的kind值
            kinds = session.scalars(stmt).all()
            return set(kinds)


