"""调查 Agent：针对一张 Incident 取证并给出结构化结论。"""
import json
import logging
from app.agent.executor import ToolExecutor
from app.agent.loop import run_agent
from app.llm.llm_client import LLMClient
from app.remediation.runbooks import RUNBOOKS
from app.storage.models import Incident
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

INVESTIGATION_PROMPT = f"""你是 ServerOpsAgent 的故障调查员，正在调查一张告警工单。

纪律：
1. 一切事实必须来自工具调用结果；区分"已确认事实"与"假设"。
2. 逐层深入：先看告警指标，再查相关服务状态与端口，必要时读服务日志。
3. 可用修复预案清单（你只能推荐其中之一，不能发明别的动作）：
{chr(10).join(f"   - {rb.name}: {rb.trigger}" for rb in RUNBOOKS)}
4. 调查结束时，你的最后一条回复必须是一个 JSON 对象（不许有其他文字），形状：
   {{"root_cause": "...", "evidence": [...], "recommended_runbook": "预案名 或 null",
    "confidence": "high|medium|low",
    "suggested_action": 可选。仅当 recommended_runbook 为 null 且你认为需要修复时给出：
      {{"description": "修复动作描述", "command": "具体 shell 命令或动作",
       "expected_effect": "预期效果", "risk_note": "风险提示"}}，
      否则为 null}}
"""


class Investigator:
    def __init__(self, llm: LLMClient, executor: ToolExecutor, registry:ToolRegistry,
                 max_steps: int = 8):
        self.llm = llm
        self.executor = executor
        self.registry = registry
        self.max_steps = max_steps

    def investigate(self, incident: Incident) -> dict | None:
        """调查一张单子。返回结论 dict；解析失败/超步返回 None（调用方决定重试）。"""
        user_message = (
            f"工单 #{incident.id}: {incident.title}\n"
            f"开单事实: {json.dumps(incident.detail, ensure_ascii=False)}\n"
            f"请调查并给出结论 JSON。"
        )
        messages = [{"role": "system", "content": INVESTIGATION_PROMPT},
                    {"role": "user", "content": user_message}]
        final = run_agent(self.llm, self.executor, self.registry, messages,
                          max_steps=self.max_steps)

        #   1) 从 final 文本中提取 JSON（提示：模型可能包了 ```json 代码块，
        #      用 final[final.find("{"):final.rfind("}")+1] 兜底再 json.loads）
        #   2) 解析失败 -> 记 warning，返回 None
        #   3) recommended_runbook 非空时，校验它在 RUNBOOKS 白名单（名字集合）里；
        #      不在 -> 记 warning，把 recommended_runbook 改为 None（幻觉防线）
        #   4) 返回结论 dict
        if final in ["（模型没有返回内容）" , "（已达到最大步数上限，任务被护栏中止。）"]:
            logger.warning("模型输出错误:%s", final)
            return None
        try:
            result = json.loads(final[final.find("{"):final.rfind("}") + 1])
        except json.decoder.JSONDecodeError:
            logger.warning("格式解析错误%s", final)
            return None
        except Exception as e:
            logger.warning(f"格式解析错误{final[:200]},错误信息{e}")
            return None

        rb_name = result.get("recommended_runbook")
        if rb_name is not None:  # 有推荐 → 校验白名单
            valid_names = {rb.name for rb in RUNBOOKS}
            if rb_name not in valid_names:
                logger.warning("Incident #%s 幻觉预案 %s 不在白名单,置 null", incident.id, rb_name)
                result["recommended_runbook"] = None  # 幻觉防线:改 null,但结论照常返回
        return result  # 无论有无预案,都返回结论

def _extract_trail(messages: list[dict]) -> list[dict]:
    """从消息史提取工具调用链。只存调用与结果摘要，不存 LLM 思考。"""
    trail = []
    step = 0
    for m in messages:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                # TODO(你来实现)：
                #   1) 找配对的结果：遍历 messages 找 role=="tool" 且
                #      tool_call_id == tc["id"] 的消息，json.loads 其 content
                #   2) 结果缺失 -> status="error", summary="（无结果）"
                #   3) 有结果 -> status=result["status"],
                #      summary=_summarize_result(result)（提炼关键字段，截断 200）
                #   4) trail.append({...}) 并 step += 1
                matched = None
                for tm in messages:
                    if tm.get("role") == "tool" and tm.get("tool_call_id") == tc["id"]:
                        matched = tm
                        break
                if matched is None:
                    # TODO 第 2 点：没找到 -> error
                    status, summary = "error", "（无结果）"
                else:
                    # TODO 第 3 点：找到了 -> 解析 content
                    try:
                        result = json.loads(matched["content"] or {})  # content 也是 JSON 字符串
                        status = result.get("status", "unknown")
                        summary = _summarize_result(result)  # 提炼摘要（下一个函数）
                    except json.JSONDecodeError:
                        status, summary = "error", "<UNK>"
                trail.append({
                    "step": step,
                    "tool": name,
                    "args": args,
                    "status": status,
                    "summary": summary,
                })
                step += 1

    return trail


def _summarize_result(result: dict) -> str:
    """从工具结果 dict 提炼一行摘要（关键字段白名单 + 截断 200）。"""
    # TODO(你来实现)：
    #   1) data = result.get("data", {})
    #   2) 从白名单字段里挑第一个存在的: state/port_open/used_pct/error/...
    #   3) 没有白名单字段 -> str(data)[:200]
    data = result.get("data",{})
    return str(data)[:200]

def _validate_suggested_action(action) -> dict | None:
    """结构化建议校验：字段齐全才保留，否则置 None（幻觉防线，同白名单思路）。"""
    if not isinstance(action, dict):
        return None
    required = ("description", "command", "expected_effect")
    if not all(action.get(k) for k in required):
        logger.warning("suggested_action 缺字段，置 None: %s", action)
        return None
    if len(action.get("command", "")) > 500:
        logger.warning("suggested_action 命令过长，置 None")
        return None
    return {k: action.get(k) for k in
            ("description", "command", "expected_effect", "risk_note")
            if action.get(k)}
