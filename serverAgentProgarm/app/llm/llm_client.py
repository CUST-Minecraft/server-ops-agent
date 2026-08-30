import time
import logging
from openai import OpenAI, APITimeoutError, APIConnectionError, RateLimitError, Stream
from openai.types.chat import ChatCompletion, ChatCompletionChunk

from app.config import LLMSettings

"""构建一个可以复用的llm对象"""
logger = logging.getLogger(__name__)

def _init_llm_client(settings:LLMSettings):
    return OpenAI(
        api_key=settings.api_key.get_secret_value(),
        base_url=settings.base_url,
        timeout=100,
    )

RETRYABLE = (APITimeoutError, APIConnectionError, RateLimitError)
MAX_RETRIES = 3

class LLMClient:
    def __init__(self):
        self.settings = LLMSettings()
        self.llm_client = _init_llm_client(self.settings)

    def chat(self, messages, tools=None)-> None | ChatCompletion | Stream[ChatCompletionChunk]:
        """调用 LLM。瞬时故障指数退避重试；不可重试错误立即抛出。"""
        #   for attempt in range(MAX_RETRIES + 1):
        #       try:
        #           （原调用逻辑，timeout 从 100 调成 30）
        #       except RETRYABLE as e:
        #           if attempt == MAX_RETRIES: raise
        #           wait = 2 ** attempt          # 1s -> 2s -> 4s
        #           logger.warning("LLM 瞬时错误(第%s次重试, 等待%ss): %s", attempt+1, wait, e)
        #           time.sleep(wait)
        #   （认证错/参数错不捕获，第一次就直接抛给调用方）
        for attempt in range(MAX_RETRIES + 1):
            try:
                kwargs = dict(messages=messages, model=self.settings.model_id)
                if tools:
                    kwargs["tools"] = tools
                response = self.llm_client.chat.completions.create(**kwargs, timeout=20)
                return response
            except RETRYABLE as e:
                if attempt == MAX_RETRIES: raise
                wait = 2 ** attempt
                logger.warning("LLM 瞬时错误(第%s次重试, 等待%ss): %s", attempt + 1, wait, e)
                time.sleep(wait)


    # 单纯连通性测试,无工具无提示词,单纯只是一个回复agent
    # def chat(self,message:list[dict],tools:list[dict] | None = None) -> dict:
    #     kwargs = dict(messages=message,model=self.settings.model_id)
    #     if tools:
    #         kwargs["tools"] = tools
    #     response = self.llm_client.chat.completions.create(**kwargs)
    #     return response


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

