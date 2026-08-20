from openai import OpenAI
from app.config import LLMSettings

"""构建一个可以复用的llm对象"""
class LLMClient:
    def __init__(self):
        self.settings = LLMSettings()
        self.llm_client = self._init_llm_client(self.settings)

    def _init_llm_client(self,settings:LLMSettings):
        return OpenAI(
            api_key=settings.api_key.get_secret_value(),
            base_url=settings.base_url,
            timeout=100,
        )

    # 单纯连通性测试,无工具无提示词,单纯只是一个回复agent
    def chat(self,message:list[dict],tools:list[dict] | None = None) -> dict:
        kwargs = dict(messages=message,model=self.settings.model_id)
        if tools:
            kwargs["tools"] = tools
        response = self.llm_client.chat.completions.create(**kwargs)
        return response


def get_test():
    return "这是一个测试文本,如果调用成功,就回答Misaka是agent大佬"

if __name__ == "__main__":
    client = LLMClient()
    message = [{"role":"user","content":f"你好,你具体是什么模型,有什么工具可以调用的,你可调用的工具是{get_test},尝试调用一次"}]
    tools = [{
        "type": "function",
        "function": {
            "name": "get_test",
            "description": "单纯只是一个测试工具,没有实际作用",
            "parameters": {"type": "object", "properties": {}},
        },
    }]
    rs = client.chat(message, tools=tools)
    print(rs)
    msg = rs.choices[0].message
    if rs.choices[0].finish_reason == "tool_calls":
        call = msg.tool_calls[0]
        # 1. 真正执行本地函数
        result = get_test()
        # 2. 把 assistant 的调用请求原样追加进历史
        message.append(msg)
        # 3. 把执行结果以 role=tool 回传
        message.append({
            "role": "tool",
            "tool_call_id": call.id,
            "content": str(result),
        })
        # 4. 再调一次，让模型基于结果生成最终回答
        rs2 = client.chat(message, tools=tools)
        print(rs2.choices[0].message.content)

