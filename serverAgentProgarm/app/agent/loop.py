"""Agent Loop：LLM 请求 -> 工具调用 -> 结果回填 -> 再请求，直到模型给出最终回答。"""
import json
import logging

from app.agent.compact import (REACTIVE_MAX_ATTEMPTS, compact_history,
                               estimate_token_count, is_context_overflow_error,
                               micro_compact, reactive_compact, snip_compact)
from app.agent.executor import ToolExecutor
from app.agent.memory import consolidate_memories, extract_memories
from app.config import ServerSettings
from app.llm.llm_client import LLMClient
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

MAX_STEPS = 10   # 护栏：一次任务最多 LLM 往返次数


def run_agent(llm: LLMClient, executor: ToolExecutor, registry: ToolRegistry,
              messages: list[dict], max_steps: int = MAX_STEPS,
              context: dict | None = None) -> str:
    """执行一轮 Agent 任务；messages 就地扩展（保留完整工具调用史）。返回最终助手文本。

    context=None （Investigator 只读路径）：老行为，不压缩不提取。
    context 给定（chat 路径）：每次调 LLM 前压缩（L1→L2→L4，便宜的先跑）；
    API 报上下文超限走 reactive 应急（限 1 次）；退出时从压缩前快照提取记忆。
    system prompt 与记忆注入归调用方（cli.py），这里不碰 messages[0]。
    """
    settings = ServerSettings() if context is not None else None
    reactive_used = 0    # reactive 应急额度：本次调用最多用 1 次
    for step in range(max_steps):
        # 压缩前快照：L4 会把历史吞成一条摘要，提取必须用完整历史（防丢）
        pre_compress = list(messages) if context is not None else None
        if context is not None:
            messages[:] = snip_compact(messages)     # L1（0 API）
            messages[:] = micro_compact(messages)    # L2（0 API）
            if estimate_token_count(messages) > settings.compact_token_threshold:
                head = messages[:1]                  # 保住 system 段，别被摘要吃掉
                try:
                    messages[:] = head + compact_history(messages[1:])   # L4（1 API）
                except Exception as e:               # 熔断/摘要失败：L1/L2 已跑，带现有历史继续
                    logger.warning("[compact] L4 不可用，本轮跳过: %s", e)

        try:
            response = llm.chat(messages, tools=registry.schemas())
        except Exception as e:
            if (context is None or reactive_used >= REACTIVE_MAX_ATTEMPTS
                    or not is_context_overflow_error(e)):
                raise                                # 非超限错误 / 应急额度用完：照抛
            reactive_used += 1
            head = messages[:1] if messages[0].get("role") == "system" else []
            messages[:] = head + reactive_compact(messages[len(head):])
            response = llm.chat(messages, tools=registry.schemas())   # 仍超限则抛异常

        choice = response.choices[0]
        message = choice.message

        if choice.finish_reason != "tool_calls":          # 对话告一段落：退出条件
            messages.append({"role": "assistant", "content": message.content or ""})
            if context is not None:
                try:
                    extract_memories(pre_compress)   # 从压缩前快照提取，自带日志
                    consolidate_memories()           # 文件数达阈值才真正整理
                except Exception as e:
                    logger.warning("[Memory] 提取/整理失败（不阻塞对话）: %s", e)
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