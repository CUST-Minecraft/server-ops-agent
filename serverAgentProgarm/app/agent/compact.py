import json
import logging

from app.llm.llm_client import LLMClient

logger = logging.getLogger(__name__)

# —— 消息形状判断（OpenAI 格式，loop.py 入史的形状）——
def _message_has_tool_use(msg: dict) -> bool:
    """assistant 消息带 tool_calls（正在发起工具调用）。"""
    return bool(msg.get("tool_calls"))

def _is_tool_result_message(msg: dict) -> bool:
    """tool 结果消息（role == "tool"，带 tool_call_id）。"""
    return msg.get("role") == "tool"

def collect_tool_result_blocks(messages: list[dict]) -> list[tuple[int, dict]]:
    """收集全部 tool 结果消息的 (下标, 消息) 列表。"""
    return [(i, m) for i, m in enumerate(messages) if _is_tool_result_message(m)]

# L1: 消息超 50 条裁中间，保留头 3 + 尾 47，不拆开 tool_use/tool_result 对
def snip_compact(messages, max_messages=50):
    if len(messages) <= max_messages:
        return messages
    head_end, tail_start = 3, len(messages) - (max_messages - 3)
    if head_end > 0 and _message_has_tool_use(messages[head_end - 1]):
        while head_end < len(messages) and _is_tool_result_message(messages[head_end]):
            head_end += 1
    if (tail_start > 0 and tail_start < len(messages)
            and _is_tool_result_message(messages[tail_start])
            and _message_has_tool_use(messages[tail_start - 1])):
        tail_start -= 1
    placeholder = {"role": "user",
                   "content": f"[snipped {tail_start - head_end} messages from conversation middle]"}
    return messages[:head_end] + [placeholder] + messages[tail_start:]

# L2: 只留最近 3 条 tool_result 完整，更旧的替换为占位符
KEEP_RECENT_TOOL_RESULTS = 3

def micro_compact(messages):
    tool_results = collect_tool_result_blocks(messages)   # [(idx, block), ...]
    if len(tool_results) <= KEEP_RECENT_TOOL_RESULTS:
        return messages
    for _, block in tool_results[:-KEEP_RECENT_TOOL_RESULTS]:
        if len(block.get("content", "")) > 120:
            block["content"] = "[Earlier tool result compacted. Re-run if needed.]"
    return messages

# token 估算：字符数/4 近似（不引 tokenizer；步骤 2 的阈值判断用）
def estimate_token_count(messages: list[dict]) -> int:
    return len(str(messages)) // 4

# L4: LLM 全量摘要（1 API；超阈值才由 loop 触发）
COMPACT_BREAKER_LIMIT = 3        # 熔断阈值：连续失败 3 次不再调用 LLM（防死循环烧钱）
_consecutive_failures = 0        # 模块级连续失败计数，成功一次即归零

def compact_history(messages):
    global _consecutive_failures
    if _consecutive_failures >= COMPACT_BREAKER_LIMIT:    # 熔断已打开：直接显式报错
        raise RuntimeError(
            f"compact_history 熔断：连续失败 {COMPACT_BREAKER_LIMIT} 次，已停止调用 LLM")
    prompt = (
        "总结这段运维 Agent 对话，让工作可以无缝继续。必须保留五要素：\n"
        "1. 当前目标 2. 关键发现/结论 3. 已执行的动作（工具调用与结果）\n"
        "4. 剩余工作 5. 用户约束与偏好。\n"
        "简洁但具体，不得发明对话里没有的信息。\n\n"
        + json.dumps(messages, ensure_ascii=False, default=str)[:80000]  # 防摘要请求自身爆上下文
    )
    try:
        llm = LLMClient()
        summary = (llm.chat(messages=[{"role": "user", "content": prompt}])
                   .choices[0].message.content or "").strip()
    except Exception as e:
        _consecutive_failures += 1
        logger.warning("compact_history 摘要失败（连续第 %d 次）: %s", _consecutive_failures, e)
        raise
    _consecutive_failures = 0
    logger.info("[compact] L4: %d 条消息 -> 摘要 %d 字符", len(messages), len(summary))
    return [{"role": "user", "content": f"[Compacted]\n\n{summary or '(empty summary)'}"}]