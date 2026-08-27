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
{{"root_cause": "一句话根因（区分事实与假设）",
  "evidence": ["事实1", "事实2"],
  "recommended_runbook": "预案名 或 null",
  "confidence": "high|medium|low"}}
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
        # TODO(你来实现) 解析结论：
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
