from types import SimpleNamespace

import app.runtime.runner as runner
from app.storage.models import RecoveryCaseRecord


def test_runner_records_case_as_derived_side_effect(db, monkeypatch):
    from tests.test_recovery_cases import _seed_verified

    _, remediation_id = _seed_verified(db)
    monkeypatch.setattr(runner, "SessionLocal", db)
    settings = SimpleNamespace(
        recovery_rag_enabled=True,
        recovery_case_origin="chaos_lab",
    )

    runner._record_recovery_outcome_if_enabled(settings, remediation_id)

    with db() as session:
        case = session.query(RecoveryCaseRecord).one()
    assert case.source_remediation_record_id == remediation_id
    assert case.origin == "chaos_lab"


def test_runner_notifies_background_indexer_after_case_record(db, monkeypatch):
    from tests.test_recovery_cases import _seed_verified

    _, remediation_id = _seed_verified(db)
    monkeypatch.setattr(runner, "SessionLocal", db)
    settings = SimpleNamespace(
        recovery_rag_enabled=True,
        recovery_case_origin="chaos_lab",
    )
    notifications = []
    coordinator = SimpleNamespace(notify=lambda: notifications.append(True))

    runner._record_recovery_outcome_if_enabled(settings, remediation_id, coordinator)

    assert notifications == [True]
