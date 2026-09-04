from app.security.policy import Decision
import app.agent.executor as executor_module
from app.tools.remediation import build_remediation_tools
from app.tools.base import Tool


def test_success_wraps_dict(executor):
    result = executor.execute("get_memory_usage")

    assert result.status == "success"
    assert result.data["used_pct"] == 71.5


def test_error_on_unknown_tool(executor):
    assert executor.execute("nope").status == "error"


def test_error_on_bad_args(executor):
    assert executor.execute("get_disk_usage", {"path": "bad"}).status == "error"


def test_write_requires_approval(executor, approvals, fake_ssh, db):
    executor.registry.register(build_remediation_tools(fake_ssh)[0])

    result = executor.execute("restart_service", {"service": "nginx"})

    assert result.status == "approval_required"
    pending = approvals.list_pending()
    assert len(pending) == 1
    assert pending[0].tool == "restart_service"
    assert fake_ssh.commands == []


def test_deny_even_when_marked_approved(executor, fake_ssh):
    executor.registry.register(build_remediation_tools(fake_ssh)[0])

    result = executor.execute(
        "restart_service",
        {"service": "nginx; shutdown"},
        approved=True,
    )

    assert result.status == "error"
    assert fake_ssh.commands == []


def test_large_dict_output_is_truncated(executor, monkeypatch):
    executor.registry.register(Tool(
        name="large_output",
        description="test",
        parameters={"type": "object", "properties": {}},
        handler=lambda _args: {"payload": "x" * 100},
    ))
    monkeypatch.setattr(executor_module, "MAX_OUTPUT_CHARS", 20)

    result = executor.execute("large_output")

    assert result.data["_truncated"] is True
    assert result.data["_original_chars"] > 20
