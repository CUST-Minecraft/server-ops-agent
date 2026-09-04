from copy import deepcopy

import pytest

from app.config import ThresholdSettings
from app.detect.detector import Detector
from app.detect.rules import build_rules


BASE = {
    "cpu_used_pct": 50.0,
    "mem_used_pct": 50.0,
    "disk_used_pct": 50.0,
    "services_status": {"ssh": "active"},
}


@pytest.fixture()
def detector():
    thresholds = ThresholdSettings(sustain=3, service_sustain=2)
    return Detector(build_rules(thresholds), thresholds.service_sustain, ["ssh"], set())


def snapshot(**changes):
    result = deepcopy(BASE)
    result.update(changes)
    return result


def test_no_event_below_threshold(detector):
    assert detector.check(snapshot()) == []
    assert detector.check(snapshot()) == []
    assert detector.check(snapshot()) == []


def test_open_after_sustain(detector):
    assert detector.check(snapshot(cpu_used_pct=90)) == []
    assert detector.check(snapshot(cpu_used_pct=90)) == []

    events = detector.check(snapshot(cpu_used_pct=90))
    assert [(event.action, event.kind) for event in events] == [("open", "cpu_used_pct")]


def test_no_duplicate_open_after_sustain(detector):
    events = []
    for _ in range(6):
        events.extend(detector.check(snapshot(cpu_used_pct=90)))

    assert [(event.action, event.kind) for event in events] == [("open", "cpu_used_pct")]


def test_recovery_resets_breach_streak(detector):
    events = []
    for value in (90, 90, 50, 90, 90, 90):
        events.extend(detector.check(snapshot(cpu_used_pct=value)))

    assert [(event.action, event.kind) for event in events] == [("open", "cpu_used_pct")]


def test_service_down_then_recovery(detector):
    assert detector.check(snapshot(services_status={"ssh": "inactive"})) == []
    opened = detector.check(snapshot(services_status={"ssh": "inactive"}))
    assert [(event.action, event.kind) for event in opened] == [("open", "service_down:ssh")]

    assert detector.check(snapshot(services_status={"ssh": "active"})) == []
    resolved = detector.check(snapshot(services_status={"ssh": "active"}))
    assert [(event.action, event.kind) for event in resolved] == [("resolve", "service_down:ssh")]
