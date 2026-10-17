from app.agent.executor import ToolExecutor
from app.remediation.runbooks import RUNBOOKS
from app.remediation.service import RemediationService
from app.remediation.verifier import Verifier
from app.security.approval import ApprovalManager
from app.security.policy import PermissionEngine
from app.storage.models import ApprovalRequest, RemediationContext, RemediationRecord
from app.tools.registry import ToolRegistry
from app.tools.remediation import build_remediation_tools


def _build_service(db, fake_ssh):
    registry = ToolRegistry()
    registry.register(build_remediation_tools(fake_ssh)[0])
    executor = ToolExecutor(registry, policy=PermissionEngine("standard"), session_factory=db)
    approvals = ApprovalManager(db, executor)
    executor.approval_manager = approvals
    return RemediationService(db, executor, Verifier(executor))


def test_remediation_context_binds_approval_and_snapshot(db, fake_ssh):
    service = _build_service(db, fake_ssh)
    snapshot = {
        "attempt": 2,
        "conclusion": {
            "root_cause": "suspected oom",
            "trail": [{"tool": "read_service_logs", "summary": "OOM killed nginx"}],
        },
    }

    result = service.execute_runbook(
        RUNBOOKS[0],
        incident_id=7,
        investigation_attempt=2,
        investigation_snapshot=snapshot,
    )

    assert result == "executed_pending_approval"
    with db() as session:
        record = session.query(RemediationRecord).one()
        context = session.query(RemediationContext).one()
        approval = session.query(ApprovalRequest).one()

    assert context.remediation_record_id == record.id
    assert context.approval_request_id == approval.id
    assert context.incident_id == 7
    assert context.investigation_attempt == 2
    assert context.investigation_snapshot == snapshot
    assert approval.incident_id == 7


def test_executor_approval_result_exposes_approval_id(db, fake_ssh):
    service = _build_service(db, fake_ssh)

    result = service.executor.execute(
        "restart_service",
        {"service": "nginx"},
        incident_id=9,
    )

    assert result.status == "approval_required"
    assert isinstance(result.data["approval_id"], int)
    with db() as session:
        approval = session.get(ApprovalRequest, result.data["approval_id"])
    assert approval.incident_id == 9


def test_remediation_service_exposes_record_id_without_changing_return_value(db, fake_ssh):
    service = _build_service(db, fake_ssh)

    result = service.execute_runbook(RUNBOOKS[0], incident_id=11)

    assert result == "executed_pending_approval"
    assert isinstance(service.last_record_id, int)
