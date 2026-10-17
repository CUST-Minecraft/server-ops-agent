"""修复执行服务：执行预案（走完整权限链）-> 确定性验证 -> 落记录。"""
import copy
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from app.storage.models import RemediationContext, RemediationRecord
from sqlalchemy.orm import sessionmaker

from app.agent.executor import ToolExecutor
from app.remediation.runbooks import Runbook
from app.remediation.verifier import Verifier, VerifyResult

logger = logging.getLogger(__name__)


class RemediationService:
    def __init__(self, session_factory: sessionmaker, executor: ToolExecutor,
                 verifier: Verifier):
        self.session_factory = session_factory
        self.executor = executor
        self.verifier = verifier
        self.last_record_id: int | None = None

    def execute_runbook(
        self,
        rb: Runbook,
        incident_id: int | None = None,
        investigation_attempt: int | None = None,
        investigation_snapshot: dict | None = None,
    ) -> str:
        """执行一个预案，返回最终状态（verified / failed / executed_pending_approval）。"""
        # TODO(你来实现) 六步：
        #   1) 落一条 RemediationRecord(status="planned") ??没看懂
        #   2) exec = self.executor.execute(rb.plan["tool"], rb.plan["args"]) √
        #      （权限链自动生效：standard 模式会返回 approval_required -- 见下方说明）
        #   3) exec.status == "approval_required" -> 记录后返回 "executed_pending_approval"
        #      （等待 Day 7 审批流：批准后由 ApprovalManager 执行，Runner 在 Day 9 接续验证）
        #   4) exec.status != "success" -> 更新记录 status="failed"、exec_status，返回
        #   5) time.sleep(3)  给服务起来的时间（进程拉起与端口监听之间有间隙）
        #   6) vr = verifier.verify(rb.postcondition) -> 按 passed 更新记录
        #      status="verified"/"failed" + verify_evidence，返回对应值
        snapshot = copy.deepcopy(investigation_snapshot or {})
        snapshot_hash = hashlib.sha256(
            json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        now = datetime.now(tz=timezone.utc)
        with self.session_factory() as session:
            record = RemediationRecord(runbook=rb.name, plan=rb.plan, status="planned",
                                       incident_id=incident_id,
                                       created_at=now)
            session.add(record)
            session.commit()
            record_id = record.id
            session.add(RemediationContext(
                remediation_record_id=record_id,
                incident_id=incident_id,
                investigation_attempt=investigation_attempt,
                investigation_snapshot=snapshot,
                snapshot_hash=snapshot_hash,
                created_at=now,
                updated_at=now,
            ))
            session.commit()
            self.last_record_id = record_id
        r = self.executor.execute(
            rb.plan["tool"], rb.plan["args"], incident_id=incident_id
        )
        if r.status == "approval_required":
            with self.session_factory() as session:
                rec = session.get(RemediationRecord, record_id)
                rec.status, rec.exec_status = "executing", r.status
                context = session.query(RemediationContext).filter_by(
                    remediation_record_id=record_id
                ).one()
                approval_id = (r.data or {}).get("approval_id")
                context.approval_request_id = approval_id
                context.updated_at = datetime.now(tz=timezone.utc)
                session.commit()
            return "executed_pending_approval"


        # ---- 4) 执行失败 ----
        if r.status != "success":
            with self.session_factory() as session:
                rec = session.get(RemediationRecord, record_id)
                rec.status, rec.exec_status = "failed", r.status
                session.commit()
            return "failed"

        # ---- 5) 给服务起来的时间 ----
        time.sleep(3)

        # ---- 6) 验证并收尾 ----
        vr = self.verifier.verify(rb.postcondition)
        with self.session_factory() as session:
            rec = session.get(RemediationRecord, record_id)
            rec.exec_status = r.status
            rec.verify_passed = vr.passed
            rec.verify_evidence = {"checks": vr.evidence}   # JSON 列要 dict，evidence 是 list
            rec.status = "verified" if vr.passed else "failed"
            session.commit()
            return str(rec.status)



