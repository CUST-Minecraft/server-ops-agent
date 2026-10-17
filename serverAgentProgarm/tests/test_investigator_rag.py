import json

from app.runtime.investigator import (
    extract_opening_facts,
    extract_available_recovery_case_refs,
    validate_recovery_case_refs,
)


def test_recovery_refs_only_include_current_tool_hits():
    messages = [
        {
            "role": "tool",
            "content": json.dumps({
                "status": "success",
                "data": {"hits": [
                    {"citation_id": "KC_current"},
                    {"citation_id": "KC_other"},
                ]},
            }),
        }
    ]

    assert extract_available_recovery_case_refs(messages) == {"KC_current", "KC_other"}
    assert validate_recovery_case_refs(
        ["KC_current", "KC_current", "KC_old", 3],
        {"KC_current", "KC_other"},
    ) == (["KC_current"], ["KC_old", 3])


def test_opening_facts_exclude_history_and_model_notes():
    class Incident:
        kind = "service_down:nginx"
        severity = "critical"
        title = "nginx down"
        detail = {
            "service": "nginx",
            "state": "inactive",
            "value": 1,
            "investigation_history": [{"root_cause": "old guess"}],
            "note": "根因: old guess",
        }

    assert extract_opening_facts(Incident()) == {
        "kind": "service_down:nginx",
        "severity": "critical",
        "title": "nginx down",
        "detail": {"service": "nginx", "state": "inactive", "value": 1},
    }
