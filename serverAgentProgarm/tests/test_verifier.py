from app.remediation.verifier import Verifier
from app.tools.base import ToolResult


class FakeExecutor:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def execute(self, tool, args):
        self.calls.append((tool, args))
        return self.results.pop(0)


def test_all_expected_values_pass_with_evidence():
    executor = FakeExecutor([ToolResult(status="success", data={"state": "active", "port": 80})])

    result = Verifier(executor).verify({
        "checks": [{"tool": "get_service_status", "args": {"service": "nginx"},
                    "expect": {"state": "active", "port": 80}}]
    })

    assert result.passed is True
    assert result.evidence[0]["ok"] is True


def test_mismatched_expectation_records_actual_value():
    executor = FakeExecutor([ToolResult(status="success", data={"state": "inactive"})])

    result = Verifier(executor).verify({
        "checks": [{"tool": "get_service_status", "args": {"service": "nginx"},
                    "expect": {"state": "active"}}]
    })

    assert result.passed is False
    assert result.evidence[0]["actual"] == {"state": "inactive"}
    assert result.evidence[0]["ok"] is False


def test_tool_error_fails_without_raising():
    executor = FakeExecutor([ToolResult(status="error", error="ssh unavailable")])

    result = Verifier(executor).verify({
        "checks": [{"tool": "get_service_status", "args": {"service": "nginx"},
                    "expect": {"state": "active"}}]
    })

    assert result.passed is False
    assert result.evidence[0]["error"] == "ssh unavailable"
