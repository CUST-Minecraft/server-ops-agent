"""Agent Loop：LLM 请求 -> 工具调用 -> 结果回填 -> 再请求，直到模型给出最终回答。"""
import json
import logging

from app.agent.executor import ToolExecutor
from app.llm.llm_client import LLMClient
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

MAX_STEPS = 10   # 护栏：一次任务最多 LLM 往返次数


def run_agent(llm: LLMClient, executor: ToolExecutor, registry: ToolRegistry,
              messages: list[dict], max_steps: int = MAX_STEPS) -> str:
    """执行一轮 Agent 任务；messages 就地扩展（保留完整工具调用史）。返回最终助手文本。"""
    for step in range(max_steps):
        response = llm.chat(messages, tools=registry.schemas())
        choice = response.choices[0]
        message = choice.message

        if choice.finish_reason != "tool_calls":          # 已给：退出条件
            messages.append({"role": "assistant", "content": message.content or ""})
            return message.content or "（模型没有返回内容）"

        #
        # 把带 tool_calls 的 assistant 消息入史。形状（协议规定，照抄即可）：
        messages.append({
              "role": "assistant",
              "content": message.content or "",
              "tool_calls": [{"id": tc.id, "type": "function",
                              "function": {"name": tc.function.name,
                                           "arguments": tc.function.arguments}}
                             for tc in message.tool_calls],
        })

        for tc in message.tool_calls :
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.decoder.JSONDecodeError as e:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id":tc.id,
                        "content": json.dumps(
                                {"status": "error", "error": f"参数不是合法 JSON: {e}", "data": None}
                            ,ensure_ascii=False
                        )
                    }
                )
                continue
            result = executor.execute(tc.function.name, args).to_dict()
            messages.append({"role": "tool", "tool_call_id": tc.id,
                              "content": json.dumps(result, ensure_ascii=False)})
            logger.info("step=%s tool=%s -> %s", step, tc.function.name, result["status"])

    return "（已达到最大步数上限，任务被护栏中止。）"