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
    logger.info("[compact] snip: 裁掉中间 %d 条消息（%d -> %d）",
                tail_start - head_end, len(messages), head_end + 1 + (len(messages) - tail_start))
    return messages[:head_end] + [placeholder] + messages[tail_start:]

# L2: 只留最近 3 条"已消费"的 tool_result 完整，更旧的替换为占位符
# （s08 适配：关在压力门后跑 + 有 target 提前停 + 排除模型还没读过的"未读"批次）
KEEP_RECENT_TOOL_RESULTS = 3

def _unseen_tool_result_indices(messages: list[dict]) -> set[int]:
    """模型还没读过的一批 tool_result——最后一条 assistant 之后追加的。
    这些是即将随本次 llm.chat 发出去的，不能占位（否则模型还没看到就被吞了）。"""
    last_assistant = max((i for i, m in enumerate(messages)
                         if m.get("role") == "assistant"), default=-1)
    return {i for i, m in enumerate(messages)
            if m.get("role") == "tool" and i > last_assistant}

def micro_compact(messages, target_tokens=None):
    """占位旧的、模型已消费过的工具结果。target_tokens 给了就降到即停（s08 的 80% 目标）。
    未读批次（最后一条 assistant 之后的）整体跳过，保证模型当轮要用的结果完整。"""
    tool_results = collect_tool_result_blocks(messages)   # [(idx, block), ...]
    unseen = _unseen_tool_result_indices(messages)
    consumed = [(i, b) for i, b in tool_results if i not in unseen]   # 只动模型已看过一轮的
    if len(consumed) <= KEEP_RECENT_TOOL_RESULTS:
        return messages
    compacted = 0
    for i, block in consumed[:-KEEP_RECENT_TOOL_RESULTS]:
        if target_tokens is not None and estimate_token_count(messages) <= target_tokens:
            break                                    # 降到目标就停，不无脑全占位
        if len(block.get("content", "")) > 120:
            block["content"] = "[Earlier tool result compacted.]"
            compacted += 1
    if compacted:
        logger.info("[compact] micro: 旧工具结果占位 %d 条", compacted)
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

# reactive: 应急压缩（API 报上下文超限才触发，不是常态路径）
REACTIVE_MAX_ATTEMPTS = 1     # 重试上限：应急压缩后仍超限，调用方直接抛异常（loop 里执行）

def is_context_overflow_error(exc: Exception) -> bool:
    """判断 API 异常是否为"上下文超限"——reactive 的唯一触发依据。
    不同厂商文案不同，按关键字匹配（Anthropic: prompt_too_long；OpenAI: context_length_exceeded）。"""
    text = str(exc).lower()
    return any(key in text for key in (
        "prompt_too_long", "context_length_exceeded",
        "maximum context length", "reduce the length"))

def reactive_compact(messages: list[dict]) -> list[dict]:
    """应急压缩：跳过阈值判断，直接上 L4 全量摘要（此刻 0 API 的 L1/L2 已证明不够用）。
    L4 不可用（含熔断已打开）时降级为激进 snip（头3+尾7，纯文本 0 API）——应急路径必须给出更短的历史，
    而不是把异常再抛回去让调用方原地死循环。"""
    logger.warning("[compact] reactive: API 报上下文超限，应急压缩 %d 条消息", len(messages))
    try:
        return compact_history(messages)
    except Exception as e:
        logger.warning("[compact] reactive: L4 摘要不可用(%s)，降级为激进 snip", e)
        return snip_compact(messages, max_messages=10)