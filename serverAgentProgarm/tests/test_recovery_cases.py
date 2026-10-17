from datetime import datetime, timezone

from app.knowledge.case_service import RecoveryCaseService
from app.storage.models import (
    Incident,
    RecoveryCaseRecord,
    RemediationContext,
    RemediationRecord,
)


def _seed_verified(db, *, remediation_id: int | None = None):
    with db() as session:
        incident = Incident(
            kind="service_down:nginx",
            severity="critical",
            status="resolved",
            title="服务 nginx 未在运行",
            detail={
                "value": 1,
                "service": "nginx",
                "state": "inactive",
                "sustain": 2,
                "snapshot_at": "2026-09-09T01:00:00+00:00",
                "investigation_history": [{"conclusion": {"root_cause": "fake"}}],
                "note": "根因: fake",
            },
            opened_at=datetime.now(timezone.utc),
            resolved_at=datetime.now(timezone.utc),
        )
        session.add(incident)
        session.flush()
        record = RemediationRecord(
            id=remediation_id,
            incident_id=incident.id,
            runbook="nginx_restart",
            plan={"tool": "restart_service", "args": {"service": "nginx"}},
            status="verified",
            exec_status="success",
            verify_passed=True,
            verify_evidence={
                "checks": [
                    {
                        "tool": "get_service_status",
                        "args": {"service": "nginx"},
                        "actual": {"active": True},
                        "expect": {"active": True},
                        "ok": True,
                    }
                ]
            },
            created_at=datetime.now(timezone.utc),
        )
        session.add(record)
        session.flush()
        session.add(RemediationContext(
            remediation_record_id=record.id,
            incident_id=incident.id,
            investigation_attempt=1,
            investigation_snapshot={
                "attempt": 1,
                "conclusion": {
                    "root_cause": "suspected oom",
                    "trail": [
                        {
                            "tool": "read_service_logs",
                            "args": {"service": "nginx"},
                            "summary": "OOM killed nginx",
                        }
                    ],
                },
            },
            snapshot_hash="snapshot-hash",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        session.commit()
        return incident.id, record.id


def test_verified_record_becomes_case_without_root_cause_in_facts(db):
    incident_id, remediation_id = _seed_verified(db)
    service = RecoveryCaseService(db, origin="chaos_lab")

    case = service.record_outcome(remediation_id)

    assert case.outcome == "verified"
    assert case.record_status == "active"
    assert case.index_status == "pending"
    assert case.source_incident_id == incident_id
    assert case.payload["opened_facts"] == {
        "value": 1,
        "service": "nginx",
        "state": "inactive",
        "sustain": 2,
        "snapshot_at": "2026-09-09T01:00:00+00:00",
    }
    assert case.model_hypothesis == "suspected oom"
    assert "fake" not in str(case.payload)


def test_record_outcome_is_idempotent(db):
    _, remediation_id = _seed_verified(db)
    service = RecoveryCaseService(db)

    first = service.record_outcome(remediation_id)
    second = service.record_outcome(remediation_id)

    assert first.id == second.id
    with db() as session:
        assert session.query(RecoveryCaseRecord).count() == 1


def test_execution_failure_is_negative_observation(db):
    _, remediation_id = _seed_verified(db)
    with db() as session:
        record = session.get(RemediationRecord, remediation_id)
        record.status = "failed"
        record.exec_status = "error"
        record.verify_passed = None
        session.commit()

    case = RecoveryCaseService(db).record_outcome(remediation_id)

    assert case.outcome == "execution_failed"
    assert case.index_status == "not_applicable"
    assert case.payload["opened_facts"]["service"] == "nginx"


def test_reconciliation_repairs_missing_case(db):
    _, remediation_id = _seed_verified(db)
    service = RecoveryCaseService(db)

    assert service.reconcile() == 1
    assert service.reconcile() == 0
    with db() as session:
        assert session.query(RecoveryCaseRecord).filter_by(
            source_remediation_record_id=remediation_id
        ).count() == 1


def test_case_builder_redacts_sensitive_tool_output(db):
    _, remediation_id = _seed_verified(db)
    with db() as session:
        context = session.query(RemediationContext).one()
        context.investigation_snapshot = {
            "attempt": 1,
            "conclusion": {
                "trail": [{
                    "tool": "read_service_logs",
                    "summary": "token=super-secret OOM killed nginx",
                }],
                "root_cause": "token=super-secret",
            },
        }
        session.commit()

    case = RecoveryCaseService(db).record_outcome(remediation_id)

    serialized = str(case.payload) + str(case.model_hypothesis)
    assert "super-secret" not in serialized
    assert "OOM" in serialized


def test_verified_case_splits_diagnosis_and_recovery_sections(db):
    _, remediation_id = _seed_verified(db)
    service = RecoveryCaseService(db)
    service.record_outcome(remediation_id)

    documents = service.index_documents()

    assert {document.section for document in documents} == {"diagnosis", "recovery"}
    assert all("outcome_scope" in document.text for document in documents)
    assert any("OOM killed nginx" in document.text for document in documents)
    assert any("nginx_restart" in document.text for document in documents)
