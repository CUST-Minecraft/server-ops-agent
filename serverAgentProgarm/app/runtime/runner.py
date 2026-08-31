"""自治闭环主进程：监控 -> 检测 -> 调查 -> 修复（过权限/审批）-> 验证 -> 关单。"""
import copy
import logging
import time
from datetime import datetime, timezone
from app import setup_logging
from app.alert import Alerter
from app.config import ServerSettings, ThresholdSettings
from app.detect.detector import Detector
from app.detect.incident_service import IncidentService
from app.detect.rules import build_rules
from app.llm.llm_client import LLMClient
from app.monitor.collector import Collector
from app.remediation.runbooks import RUNBOOKS
from app.remediation.service import RemediationService
from app.remediation.verifier import Verifier
from app.runtime.investigator import Investigator
from app.security.approval import ApprovalManager
from app.storage.db import SessionLocal, init_db
from app.storage.models import ApprovalRequest, Incident, MetricSnapshot, RemediationRecord

logger = logging.getLogger(__name__)


def run() -> None:
    setup_logging()
    settings = ServerSettings()
    init_db()

    # ---- 装配（全部是老朋友）----
    from app.runtime_deps import build_executor_and_approvals
    executor, registry, approvals = build_executor_and_approvals()
    thresholds = ThresholdSettings()
    services = [s.strip() for s in settings.watched_services.split(",") if s.strip()]

    alerter = Alerter(settings.alert_webhook_url)
    incident_service = IncidentService(SessionLocal,alerter=alerter)

    detector = Detector(build_rules(thresholds), thresholds.service_sustain, services,
                        open_kinds=incident_service.find_open_kind_set())
    collector = Collector(executor, services)
    investigator = Investigator(LLMClient(), executor, registry)
    remediation = RemediationService(SessionLocal, executor, Verifier(executor))

    logger.info("自治闭环已启动 mode=%s interval=%ss", settings.policy_mode,
                settings.monitor_interval)

    while True:
        try:
            tick(collector, detector, incident_service, approvals, investigator,
                 remediation, settings)
        except Exception:                     # noqa: BLE001  值班进程不许死
            logger.exception("tick 失败（继续运行）")
        time.sleep(settings.monitor_interval)


def tick(collector: Collector, detector: Detector,
         incident_service: IncidentService, approvals: ApprovalManager,
         investigator: Investigator, remediation: RemediationService,
         settings: ServerSettings) -> None:
    # ---- 1) 采集快照 + 入库 ----
    snap = collector.collect()
    with SessionLocal() as session:
        session.add(MetricSnapshot(
            collected_at=snap["collected_at"],
            cpu_used_pct=snap["cpu_used_pct"],
            load_1m=snap["load_1m"],
            load_5m=snap["load_5m"],
            load_15m=snap["load_15m"],
            mem_used_pct=snap["mem_used_pct"],
            mem_available_mb=snap["mem_available_mb"],
            disk_used_pct=snap["disk_used_pct"],
            services_status=snap["services_status"],
        ))
        session.commit()
    logger.info("快照入库 cpu=%.1f%% mem=%.1f%% disk=%.1f%% services=%s",
                snap["cpu_used_pct"], snap["mem_used_pct"], snap["disk_used_pct"],
                snap["services_status"])

    # ---- 2) 检测 -> 开/关单 ----
    events = detector.check(snap)
    if events:
        incident_service.apply(events)
        logger.warning("检测到事件: %s", events)

    # ---- 3) 清扫过期审批单 ----
    expired = approvals.expire_stale()
    if expired:
        logger.warning("清扫过期审批单 %s 张", expired)

    # ---- 4) 对每张 open 且未调查完的单：调查 -> 选预案 -> 执行 ----
    with SessionLocal() as session:
        open_incidents = (session.query(Incident)
                          .filter(Incident.status == "open")
                          .order_by(Incident.id).all())
        # 取到 detached 对象的 id 列表（commit 后 session 关闭再查会失效，按 id 重查）
        open_ids = [inc.id for inc in open_incidents]

    for inc_id in open_ids:
        _handle_open(inc_id, incident_service, investigator, remediation, settings)

    # ---- 5) 对每张 awaiting_approval 的单：查审批单状态 -> 接续验证/失败 ----
    with SessionLocal() as session:
        pending_incidents = (session.query(Incident)
                             .filter(Incident.status == "awaiting_approval")
                             .order_by(Incident.id).all())
        pending_ids = [inc.id for inc in pending_incidents]

    for inc_id in pending_ids:
        _handle_awaiting(inc_id, incident_service, remediation)


def _handle_open(inc_id: int, incident_service: IncidentService,
                 investigator: Investigator, remediation: RemediationService,
                 settings: ServerSettings) -> None:
    """步骤 4：调查一张 open 单子，有预案则执行，无预案则回退重试。"""
    # 先转 investigating（合法转移：open -> investigating）
    if not incident_service.update_status(inc_id, "investigating", note="Runner 开始调查"):
        logger.warning("Incident #%s 转 investigating 失败（可能已被处理）", inc_id)
        return

    with SessionLocal() as session:
        inc = session.get(Incident, inc_id)
        if inc is None:
            logger.warning("Incident #%s 不存在", inc_id)
            return
        detail = dict(inc.detail)              # 拷贝出来，避免 in-place 改动不被 ORM 跟踪
        retry = detail.get("investigate_retry_count", 0)

    # 调查
    with SessionLocal() as session:
        inc = session.get(Incident, inc_id)
        conclusion = investigator.investigate(inc)

    if conclusion is None:
        # 调查失败（解析不了/超步）：重试计数 +1，超上限则 failed，否则回退 open
        retry += 1
        if retry >= settings.investigate_max_retries:
            incident_service.update_status(inc_id, "failed",
                                           note=f"调查失败 {retry} 次，超过上限")
            logger.warning("Incident #%s 调查失败 %s 次，标记 failed", inc_id, retry)
        else:
            _write_detail(inc_id, {"investigate_retry_count": retry})
            incident_service.update_status(inc_id, "open",
                                           note=f"调查失败，第 {retry} 次重试")
            logger.warning("Incident #%s 调查失败，回退 open 重试（第 %s 次）", inc_id, retry)
        return

    # 调查成功

    history = copy.deepcopy(inc.detail.get("investigation_history", []))

    # 追加本次调查（结论含 trail / suggested_action）
    history.append({
        "attempt": len(history) + 1,
        "at": datetime.now(timezone.utc).isoformat(),
        "conclusion": conclusion,
    })
    history = history[-10:]                    # 上限保护：最多 10 条，超出丢最旧


    rb_name = conclusion.get("recommended_runbook")
    root_cause = conclusion.get("root_cause", "")

    if rb_name is None:
        # 无推荐预案（查不清/不需要修）：计一次重试，超上限则 failed（防无限循环）
        retry += 1
        _write_detail(inc_id, {"investigation_history": history,
                               "investigate_retry_count": retry})
        if retry >= settings.investigate_max_retries:
            incident_service.update_status(inc_id, "failed",
                                           note=f"无推荐预案 {retry} 次，超过上限，需人工介入")
            logger.warning("Incident #%s 无推荐预案 %s 次，标记 failed 需人工介入",
                           inc_id, retry)
        else:
            incident_service.update_status(inc_id, "open",
                                           note=f"无推荐预案，第 {retry} 次重试")
            logger.info("Incident #%s 调查完成但无预案，回退 open 重试（第 %s 次）",
                        inc_id, retry)
        return

    # 有预案：history 写回 detail，重置重试计数
    _write_detail(inc_id, {"investigation_history": history, "investigate_retry_count": 0})

    # 有推荐预案：找到 RUNBOOKS 里对应的项
    rb = next((r for r in RUNBOOKS if r.name == rb_name), None)
    if rb is None:
        incident_service.update_status(inc_id, "open",
                                       note=f"预案 {rb_name} 不在 RUNBOOKS，回退重试")
        logger.warning("Incident #%s 预案 %s 不在 RUNBOOKS", inc_id, rb_name)
        return

    # 执行预案（走完整权限链：standard 会挂起成审批单）
    outcome = remediation.execute_runbook(rb, incident_id=inc_id)
    if outcome == "verified":
        incident_service.update_status(inc_id, "resolved", note=f"根因: {root_cause}")
        logger.info("Incident #%s 修复验证通过，已 resolved", inc_id)
    elif outcome == "failed":
        incident_service.update_status(inc_id, "failed", note="预案执行失败")
        logger.warning("Incident #%s 预案 %s 执行失败", inc_id, rb_name)
    elif outcome == "executed_pending_approval":
        incident_service.update_status(inc_id, "awaiting_approval",
                                       note=f"待审批: {rb_name}")
        logger.info("Incident #%s 待审批（预案 %s），转 awaiting_approval", inc_id, rb_name)
    else:
        logger.warning("Incident #%s 未知 outcome: %s", inc_id, outcome)


def _handle_awaiting(inc_id: int, incident_service: IncidentService,
                     remediation: RemediationService) -> None:
    """步骤 5：查关联审批单状态，approved 则补验证，rejected/expired 则 failed。"""
    with SessionLocal() as session:
        # 查该 incident 最新一张关联审批单（incident_id 匹配、按 id 倒序第一条）
        req = (session.query(ApprovalRequest)
               .filter(ApprovalRequest.incident_id == inc_id)
               .order_by(ApprovalRequest.id.desc()).first())
        if req is None:
            # 没有关联审批单（数据不一致），回退 open 重查
            incident_service.update_status(inc_id, "open", note="无关联审批单，回退重试")
            logger.warning("Incident #%s awaiting_approval 但无关联审批单", inc_id)
            return
        req_status = req.status          # pending / approved / rejected / expired
        req_result = req.result_status   # 执行结果（approved 后填）

    if req_status == "pending":
        # 人还没来，什么都不做
        logger.info("Incident #%s 审批单待批，等待人", inc_id)
        return

    if req_status in ("rejected", "expired"):
        # 人拒绝 / 审批过期 -> failed（不重试：人拒绝 ≠ 再试一次）
        incident_service.update_status(inc_id, "failed",
                                       note=f"审批单 {req_status}，单子标记 failed")
        logger.warning("Incident #%s 审批单 %s，标记 failed", inc_id, req_status)
        return

    if req_status == "approved":
        # 已批准：接续验证（昨天的缝隙在这里补上）
        if req_result != "success":
            # 执行本身失败（虽然批了，但 restart 没跑通）
            incident_service.update_status(inc_id, "failed",
                                           note=f"已批准但执行结果 {req_result}")
            logger.warning("Incident #%s 已批准但执行失败: %s", inc_id, req_result)
            return

        # 执行成功，补做后置条件验证
        # 找到该 incident 用的是哪个 runbook（从 remediation_records 查最新一条）
        with SessionLocal() as session:
            record = (session.query(RemediationRecord)
                      .filter(RemediationRecord.incident_id == inc_id)
                      .order_by(RemediationRecord.id.desc()).first())
        if record is None:
            incident_service.update_status(inc_id, "failed", note="无修复记录，无法验证")
            logger.warning("Incident #%s approved 但无修复记录", inc_id)
            return

        rb = next((r for r in RUNBOOKS if r.name == record.runbook), None)
        if rb is None:
            incident_service.update_status(inc_id, "failed",
                                           note=f"预案 {record.runbook} 不在 RUNBOOKS")
            logger.warning("Incident #%s 修复记录的预案 %s 不在 RUNBOOKS", inc_id, record.runbook)
            return

        # 补做验证
        vr = remediation.verifier.verify(rb.postcondition)
        # 把验证结果回写到修复记录
        with SessionLocal() as session:
            rec = session.get(RemediationRecord, record.id)
            if rec is not None:
                rec.verify_passed = vr.passed
                rec.verify_evidence = {"checks": vr.evidence}
                rec.status = "verified" if vr.passed else "failed"
                session.commit()

        if vr.passed:
            incident_service.update_status(inc_id, "resolved",
                                           note=f"审批后验证通过: {rb.name}")
            logger.info("Incident #%s 审批后验证通过，已 resolved", inc_id)
        else:
            incident_service.update_status(inc_id, "failed",
                                           note=f"审批后验证失败: {rb.name}")
            logger.warning("Incident #%s 审批后验证失败", inc_id)
        return

    # 其他未知状态
    logger.warning("Incident #%s 审批单未知状态: %s", inc_id, req_status)


def _write_detail(inc_id: int, updates: dict) -> None:
    """把 updates 合并进 incident.detail（深拷贝后重新赋值，确保 ORM 跟踪到嵌套变更）。"""
    with SessionLocal() as session:
        inc = session.get(Incident, inc_id)
        if inc is None:
            return
        detail = copy.deepcopy(inc.detail)
        detail.update(updates)
        inc.detail = detail            # 重新赋值，触发 SQLAlchemy JSON 列变更检测
        session.commit()


if __name__ == "__main__":
    run()
