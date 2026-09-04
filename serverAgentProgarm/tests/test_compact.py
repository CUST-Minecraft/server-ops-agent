import pytest

import app.agent.compact as compact


def test_snip_compact_obeys_maximum_message_count():
    messages = [{"role": "user", "content": f"m{i}"} for i in range(51)]

    result = compact.snip_compact(messages, max_messages=50)

    assert len(result) <= 50
    assert result[:3] == messages[:3]
    assert "[snipped" in result[3]["content"]


def test_snip_compact_never_keeps_only_half_of_a_tool_call_pair():
    messages = [{"role": "user", "content": f"m{i}"} for i in range(52)]
    messages[5] = {"role": "assistant", "content": "calling", "tool_calls": [{"id": "call-1"}]}
    messages[6] = {"role": "tool", "tool_call_id": "call-1", "content": "result"}

    result = compact.snip_compact(messages, max_messages=50)

    kept_call = any(message.get("tool_calls") for message in result)
    kept_result = any(message.get("tool_call_id") == "call-1" for message in result)
    assert len(result) <= 50
    assert kept_call is kept_result


def test_micro_compact_keeps_the_latest_three_consumed_results():
    messages = [{"role": "assistant", "content": "called", "tool_calls": [{"id": "call"}]}]
    messages.extend({"role": "tool", "tool_call_id": f"call-{i}", "content": "x" * 121} for i in range(5))
    messages.append({"role": "assistant", "content": "done"})

    compact.micro_compact(messages, target_tokens=0)

    assert [message["content"] for message in messages[1:3]] == [
        "[Earlier tool result compacted.]",
        "[Earlier tool result compacted.]",
    ]
    assert all(message["content"] == "x" * 121 for message in messages[3:6])


@pytest.mark.parametrize("text,expected", [
    ("prompt_too_long", True),
    ("context_length_exceeded", True),
    ("maximum context length", True),
    ("rate limit", False),
])
def test_context_overflow_classifier(text, expected):
    assert compact.is_context_overflow_error(Exception(text)) is expected


def test_reactive_compact_fallback_respects_aggressive_limit(monkeypatch):
    messages = [{"role": "user", "content": f"m{i}"} for i in range(11)]
    monkeypatch.setattr(compact, "compact_history", lambda _messages: (_ for _ in ()).throw(RuntimeError("offline")))

    result = compact.reactive_compact(messages)

    assert len(result) <= 10


def test_token_estimate_is_non_negative():
    assert compact.estimate_token_count([]) >= 0
