from app.tools.remediation import build_remediation_tools


def create_pending(executor, approvals, fake_ssh):
    if executor.registry.get("restart_service") is None:
        executor.registry.register(build_remediation_tools(fake_ssh)[0])
    result = executor.execute("restart_service", {"service": "nginx"})
    assert result.status == "approval_required"
    return approvals.list_pending()[0]


def test_approve_executes_and_records_actor(executor, approvals, fake_ssh, db):
    request = create_pending(executor, approvals, fake_ssh)

    approvals.approve(request.id, actor="alice")

    with db() as session:
        saved = session.get(type(request), request.id)
    assert saved.status == "approved"
    assert saved.decided_by == "alice"
    assert saved.result_status == "success"
    assert any("systemctl restart nginx" in command for command in fake_ssh.commands)


def test_second_approval_is_rejected(executor, approvals, fake_ssh):
    request = create_pending(executor, approvals, fake_ssh)

    approvals.approve(request.id)
    result = approvals.approve(request.id)

    assert "已过期/已处理" in result
    assert len(fake_ssh.commands) == 1


def test_expired_approval_does_not_execute(executor, db, fake_ssh):
    from app.security.approval import ApprovalManager

    executor.registry.register(build_remediation_tools(fake_ssh)[0])
    approvals = ApprovalManager(db, executor, ttl_minutes=0)
    executor.approval_manager = approvals
    request = create_pending(executor, approvals, fake_ssh)

    result = approvals.approve(request.id)

    assert "已经过期" in result
    assert fake_ssh.commands == []


def test_reject_records_actor_without_executing(executor, approvals, fake_ssh, db):
    request = create_pending(executor, approvals, fake_ssh)

    approvals.reject(request.id, actor="bob")

    with db() as session:
        saved = session.get(type(request), request.id)
    assert saved.status == "rejected"
    assert saved.decided_by == "bob"
    assert fake_ssh.commands == []


def test_tampered_approval_never_executes(executor, approvals, fake_ssh, db):
    request = create_pending(executor, approvals, fake_ssh)
    with db() as session:
        saved = session.get(type(request), request.id)
        saved.args = {"service": "mysql"}
        session.commit()

    result = approvals.approve(request.id)

    assert "参数被篡改" in result
    assert fake_ssh.commands == []
