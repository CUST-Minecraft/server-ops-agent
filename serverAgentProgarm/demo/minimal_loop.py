"""Day 3 最小 Demo：解剖一次工具调用请求（不执行任何真实工具）。"""
from app.llm.llm_client import LLMClient

FAKE_TOOLS = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "查询指定城市的天气",
        "parameters": {"type": "object",
                       "properties": {"city": {"type": "string", "description": "城市名"}},
                       "required": ["city"]},
    },
}]

if __name__ == "__main__":
    llm = LLMClient()
    messages = [{"role": "user", "content": "上海和北京天气呢？"}]
    resp = llm.chat(messages, tools=FAKE_TOOLS)
    choice = resp.choices[0]
    print("finish_reason =", choice.finish_reason)          # 'tool_calls'
    print("content       =", choice.message.content)        # None 或一段说明文字
    for tc in choice.message.tool_calls or []:
        print("tool_call.id  =", tc.id)
        print("name          =", tc.function.name)          # 'get_weather'
        print("arguments     =", tc.function.arguments)     # '{"city": "北京"}'  <- 是字符串！