"""检测器：快照流 -> 确认事件（纯逻辑，不碰数据库）。"""
import logging
from collections import defaultdict
from dataclasses import dataclass

from app.config import ServerSettings, ThresholdSettings
from app.detect.rules import Rule, build_rules

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DetectEvent:
    """检测器输出的确认事件。action: "open" 或 "resolve"。"""
    action: str
    kind: str            # 规则 key 或 "service_down:<name>"
    severity: str
    title: str
    detail: dict         # 现场摘录


class Detector:
    """有状态：内部维护连击计数，每次 check() 喂一个快照。"""

    def __init__(self, rules: list[Rule], service_sustain: int, watched_services: list[str],open_kinds: set[str]):
        self.rules = rules
        self.open_kinds  = open_kinds # 已经开单的kind
        self.service_sustain = service_sustain
        self.watched_services = watched_services
        self._breach_streak: dict[str, int] = defaultdict(int)   # 越界连击
        self._ok_streak: dict[str, int] = defaultdict(int)       # 恢复连击

    def check(self, snap: dict) -> list[DetectEvent]:
        events: list[DetectEvent] = []
        for rule in self.rules:                      # 1) 资源规则
            value = snap.get(rule.key)
            if value is None:
                continue                              # 字段缺失：本轮跳过（半快照已被 Day4 拦截）
            breached = value > rule.threshold if rule.op == ">" else value < rule.threshold
            events.append(self._track(rule.key, breached, rule, snap))
        for svc, state in snap.get("services_status", {}).items():   # 2) 服务规则
            events.append(self._track(f"service_down:{svc}", state != "active",
                                      Rule(key=f"service_down:{svc}", op=">", threshold=1,
                                           sustain=self.service_sustain, severity="critical",
                                           title=f"服务 {svc} 未在运行"),
                                      snap, extra={"service": svc, "state": state}))
        return [e for e in events if e is not None]

    def _track(self, kind: str, breached: bool, rule: Rule, snap: dict,
               extra: dict | None = None) -> DetectEvent | None:
        if breached:                                            # 越界分支已给
            self._ok_streak[kind] = 0
            self._breach_streak[kind] += 1
            if self._breach_streak[kind] == rule.sustain:    # == 而不是 >=：只在到达时发一次
                self.open_kinds.add(kind)
                return DetectEvent("open", kind, rule.severity, rule.title,
                                   detail={"value": snap.get(rule.key), **(extra or {}),
                                           "sustain": rule.sustain,
                                           "snapshot_at": str(snap.get("collected_at"))})
        else:
            #   1) 清零越界连击，累加恢复连击
            #   2) 恢复连击恰好 == rule.sustain 时，返回
            #      DetectEvent("resolve", kind, rule.severity, rule.title, detail={**(extra or {})})
            #   （注意同样用 == 不用 >=：恢复也只发一次事件）
            self._ok_streak[kind] += 1
            self._breach_streak[kind] = 0
            if self._ok_streak[kind] == rule.sustain and kind in self.open_kinds:
                return DetectEvent("resolve", kind, rule.severity, rule.title,detail={**(extra or {})})

        return None