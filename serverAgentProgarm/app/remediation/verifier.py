"""确定性验证器：只读工具 + 断言，绝不询问 LLM。"""
import logging
from dataclasses import dataclass, field

from app.agent.executor import ToolExecutor

logger = logging.getLogger(__name__)


@dataclass
class VerifyResult:
    passed: bool
    evidence: list[dict] = field(default_factory=list)   # 每个 check 的实际值（报告素材）


class Verifier:
    def __init__(self, executor: ToolExecutor):
        self.executor = executor

    def verify(self, postcondition: dict) -> VerifyResult:
        result = VerifyResult(passed=True)
        for check in postcondition.get("checks", []):
            # TODO(你来实现) 对每个 check：
            #   1) r = executor.execute(check["tool"], check["args"])
            #   2) 若 r.status != "success"：记 evidence {"check": ..., "error": r.error}
            #      并判 failed
            #   3) 否则逐键比对 expect：expect 的每个 k,v 必须等于 r.data.get(k)
            #      全部相等 -> 该 check 通过；任何不等 -> failed，evidence 记实际值
            #   4) evidence 每项形如 {"tool": ..., "args": ..., "expect": ...,
            #      "actual": r.data, "ok": True/False}
            r = self.executor.execute(check["tool"], check["args"])
            if r.status != "success":
                result.passed = False
                result.evidence.append({
                    "tool": check["tool"],
                     "args": check["args"],
                     "expect": check.get("expect"),
                     "actual": None,
                     "error": r.error,
                     "ok": False
                })
                continue
            expect = check.get("expect",{})
            ok = all(r.data.get(k) == v for k, v in expect.items())
            if not ok:
                result.passed = False
            result.evidence.append({"tool": check["tool"], "args": check["args"],
                                    "expect": expect, "actual": r.data, "ok": ok})

        return result