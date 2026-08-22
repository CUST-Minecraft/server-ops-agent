"""检测规则：什么指标、什么条件、连续几次、什么级别。"""
from dataclasses import dataclass
from app.config import ThresholdSettings


@dataclass(frozen=True)
class Rule:
    key: str            # 快照字段名，如 "cpu_used_pct"（也是规则的唯一标识/去重键）
    op: str             # ">" 或 "<"
    threshold: float    # 阈值
    sustain: int        # 连续命中次数才确认
    severity: str       # "warning" | "critical"
    title: str          # 人话标题，开单时直接用


DEFAULT_RULES = [
    Rule(key="cpu_used_pct", op=">", threshold=85, sustain=3, severity="warning",
         title="CPU 使用率过高"),
    Rule(key="mem_used_pct", op=">", threshold=85, sustain=3, severity="warning",
         title="内存使用率过高"),
    Rule(key="disk_used_pct", op=">", threshold=80, sustain=3, severity="warning",
         title="磁盘使用率过高"),
]



def build_rules(t: ThresholdSettings) -> list[Rule]:
    """从阈值配置合成资源规则；服务规则在 Detector 内部处理。"""
    return [
        Rule(key="cpu_used_pct", op=">", threshold=t.cpu_pct, sustain=t.sustain,
             severity="warning", title="CPU 使用率过高"),
        Rule(key="mem_used_pct", op=">", threshold=t.mem_pct, sustain=t.sustain,
             severity="warning", title="内存使用率过高"),
        Rule(key="disk_used_pct", op=">", threshold=t.disk_pct, sustain=t.sustain,
             severity="warning", title="磁盘使用率过高"),
    ]