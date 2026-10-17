"""Build and reconcile deterministic recovery cases from remediation records."""

from __future__ import annotations

import copy
from datetime import datetime, timezone

from sqlalchemy.orm import sessionmaker

from app.knowledge.models import IndexDocument
from app.knowledge.normalization import build_occurrence_signature, canonical_json, redact_text, sha256_text
from app.storage.models import (
    Incident,
    RecoveryCaseRecord,
    RemediationContext,
    RemediationRecord,
)


OPEN_FACT_KEYS = ("value", "service", "state", "sustain", "snapshot_at")


def _canonical(value: object) -> str:
    return canonical_json(value)


def _hash(value: object) -> str:
    return sha256_text(_canonical(value))


def _redact_value(value: object) -> object:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact_value(item) for key, item in value.items()}
    return value


def _outcome(record: RemediationRecord) -> str:
    if record.status == "verified" and record.verify_passed is True:
        return "verified"
    if record.status == "failed" and record.exec_status == "success" and record.verify_passed is False:
        return "verification_failed"
    return "execution_failed"


class RecoveryCaseService:
    def __init__(self, session_factory: sessionmaker, origin: str = "real"):
        self.session_factory = session_factory
        self.origin = origin

    def record_outcome(self, remediation_record_id: int) -> RecoveryCaseRecord:
        with self.session_factory() as session:
            existing = session.query(RecoveryCaseRecord).filter_by(
                source_remediation_record_id=remediation_record_id
            ).one_or_none()
            if existing is not None:
                return existing

            record = session.get(RemediationRecord, remediation_record_id)
            if record is None:
                raise ValueError(f"修复记录不存在: {remediation_record_id}")
            context = session.query(RemediationContext).filter_by(
                remediation_record_id=remediation_record_id
            ).one_or_none()
            incident = session.get(Incident, record.incident_id) if record.incident_id else None

            if context is None or incident is None:
                case = RecoveryCaseRecord(
                    source_incident_id=record.incident_id,
                    source_remediation_record_id=record.id,
                    origin=self.origin,
                    outcome=_outcome(record),
                    record_status="quarantined",
                    index_status="not_applicable",
                    payload={},
                    failure_reason="缺少 Incident 或 RemediationContext，无法建立完整证据链",
                    created_at=datetime.now(timezone.utc),
                )
                session.add(case)
                session.commit()
                return case

            snapshot = copy.deepcopy(context.investigation_snapshot or {})
            conclusion = snapshot.get("conclusion") if isinstance(snapshot, dict) else {}
            conclusion = conclusion if isinstance(conclusion, dict) else {}
            opened_detail = incident.detail if isinstance(incident.detail, dict) else {}
            opened_facts = {
                key: opened_detail[key]
                for key in OPEN_FACT_KEYS
                if key in opened_detail
            }
            trail = conclusion.get("trail", [])
            trail = trail if isinstance(trail, list) else []
            trail = _redact_value(trail)
            verification = (record.verify_evidence or {}).get("checks", [])
            verification = verification if isinstance(verification, list) else []
            verification = _redact_value(verification)
            outcome = _outcome(record)
            payload = {
                "opened_facts": opened_facts,
                "diagnostic_steps": trail,
                "verification": verification,
                "outcome_scope": "postconditions_recovered_not_root_cause_proven",
                "origin": self.origin,
            }
            runbook_hash = _hash({"runbook": record.runbook, "plan": record.plan})
            signature = build_occurrence_signature({
                "kind": incident.kind,
                "service": opened_facts.get("service"),
                "tools": sorted(
                    str(step.get("tool")) for step in trail if isinstance(step, dict)
                ),
                "states": {
                    key: opened_facts.get(key)
                    for key in ("state", "value")
                    if key in opened_facts
                },
                "runbook": record.runbook,
                "runbook_hash": runbook_hash,
            })
            case = RecoveryCaseRecord(
                source_incident_id=incident.id,
                source_remediation_record_id=record.id,
                origin=self.origin,
                outcome=outcome,
                record_status="active",
                index_status="pending" if outcome == "verified" else "not_applicable",
                payload=payload,
                model_hypothesis=redact_text(str(conclusion.get("root_cause", ""))) or None,
                executed_runbook=record.runbook,
                runbook_hash=runbook_hash,
                occurrence_signature=signature,
                content_hash=_hash(payload),
                aggregate_dirty=outcome != "verified",
                created_at=datetime.now(timezone.utc),
            )
            session.add(case)
            session.commit()
            return case

    def reconcile(self) -> int:
        with self.session_factory() as session:
            record_ids = [
                row.id
                for row in session.query(RemediationRecord)
                .filter(RemediationRecord.status.in_(("verified", "failed")))
                .all()
                if session.query(RecoveryCaseRecord).filter_by(
                    source_remediation_record_id=row.id
                ).one_or_none() is None
            ]
        for record_id in record_ids:
            self.record_outcome(record_id)
        return len(record_ids)

    def index_documents(self) -> list[IndexDocument]:
        """Build contextual diagnosis/recovery chunks from active case groups."""
        with self.session_factory() as session:
            rows = session.query(RecoveryCaseRecord).filter(
                RecoveryCaseRecord.record_status == "active",
            ).all()
            grouped: dict[tuple[str, str], dict] = {}
            for row in rows:
                signature = row.occurrence_signature or f"record-{row.id}"
                key = (signature, row.origin)
                item = grouped.setdefault(key, {
                    "parent_case_id": f"case-{row.id}",
                    "source_incident_ids": [],
                    "origin": row.origin,
                    "signature": signature,
                    "service": None,
                    "facts": {},
                    "steps": [],
                    "verification": [],
                    "runbook": "",
                    "passed_count": 0,
                    "failed_count": 0,
                })
                if row.source_incident_id and row.source_incident_id not in item["source_incident_ids"]:
                    item["source_incident_ids"].append(row.source_incident_id)
                if row.outcome != "verified":
                    item["failed_count"] += 1
                    continue
                payload = row.payload or {}
                facts = payload.get("opened_facts", {})
                steps = payload.get("diagnostic_steps", [])
                verification = payload.get("verification", [])
                if not item["facts"]:
                    item["facts"] = facts
                    item["steps"] = steps
                    item["verification"] = verification
                    item["runbook"] = row.executed_runbook or ""
                    item["service"] = facts.get("service") if isinstance(facts, dict) else None
                    item["parent_case_id"] = f"case-{row.id}"
                item["passed_count"] += 1
            documents: list[IndexDocument] = []
            for item in grouped.values():
                if not item["facts"]:
                    continue
                context = (
                    "case_context "
                    f"origin={item['origin']} service={item['service']} "
                    f"signature={item['signature']} "
                    f"passed_count={item['passed_count']} "
                    f"failed_count={item['failed_count']} "
                    "outcome_scope=postconditions_recovered_not_root_cause_proven"
                )
                common = {
                    "source_incident_ids": tuple(item["source_incident_ids"]),
                    "origin": item["origin"],
                    "signature": item["signature"],
                    "service": item["service"],
                    "passed_count": item["passed_count"],
                    "failed_count": item["failed_count"],
                    "parent_case_id": item["parent_case_id"],
                }
                documents.extend([
                    IndexDocument(
                        case_id=f"{item['parent_case_id']}:diagnosis",
                        section="diagnosis",
                        text=(
                            f"{context}\nsection=diagnosis\n"
                            f"opened_facts={item['facts']}\n"
                            f"diagnostic_steps={item['steps']}"
                        ),
                        **common,
                    ),
                    IndexDocument(
                        case_id=f"{item['parent_case_id']}:recovery",
                        section="recovery",
                        text=(
                            f"{context}\nsection=recovery\n"
                            f"executed_runbook={item['runbook']}\n"
                            f"verification={item['verification']}"
                        ),
                        **common,
                    ),
                ])
            return documents
