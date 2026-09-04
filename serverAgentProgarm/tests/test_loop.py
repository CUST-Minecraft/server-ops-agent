import json

from app.agent.loop import run_agent
from tests.conftest import FakeLLM


def test_loop_full_tool_trajectory(registry, executor):
    llm = FakeLLM([
        ("tool_calls", [("get_cpu_status", "{}", "call_1")]),
        ("stop", "CPU 正常。"),
    ])
    messages = [{"role": "user", "content": "看看 CPU"}]

    answer = run_agent(llm, executor, registry, messages)

    assert answer == "CPU 正常。"
    assert [message["role"] for message in messages] == ["user", "assistant", "tool", "assistant"]
    assert messages[2]["tool_call_id"] == "call_1"
    assert json.loads(messages[2]["content"])["status"] == "success"


def test_loop_stops_without_tools(registry, executor):
    llm = FakeLLM([("stop", "直接回答")])
    messages = [{"role": "user", "content": "hi"}]

    assert run_agent(llm, executor, registry, messages) == "直接回答"
    assert [message["role"] for message in messages] == ["user", "assistant"]


def test_loop_returns_tool_error_for_malformed_arguments(registry, executor):
    llm = FakeLLM([
        ("tool_calls", [("get_cpu_status", "{", "call_bad")]),
        ("stop", "参数已修正"),
    ])
    messages = [{"role": "user", "content": "看看 CPU"}]

    answer = run_agent(llm, executor, registry, messages)

    assert answer == "参数已修正"
    payload = json.loads(messages[2]["content"])
    assert payload["status"] == "error"
    assert "参数不是合法 JSON" in payload["error"]


def test_loop_stops_at_max_steps(registry, executor):
    llm = FakeLLM([("tool_calls", [("get_cpu_status", "{}", "call_1")])])
    messages = [{"role": "user", "content": "看看 CPU"}]

    assert run_agent(llm, executor, registry, messages, max_steps=1) == "（已达到最大步数上限，任务被护栏中止。）"
