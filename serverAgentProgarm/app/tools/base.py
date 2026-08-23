from typing import Callable
from dataclasses import dataclass

@dataclass
class ToolResult:
    """工具执行的统一结果。status 三态：
    - success:    拿到了数据
    - error:      执行出错（异常/命令失败/解析失败）
    - no_data:    执行成功但无有效数据（如服务没有日志）
    """
    status: str                 # "success" | "error" | "no_data"
    data: dict | None = None
    error: str | None = None
    invocation: str = ""        # 可追溯：实际执行了什么
    elapsed_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "data": self.data,
            "error": self.error,
            "invocation": self.invocation,
            "elapsed_ms": self.elapsed_ms,
        }

@dataclass
class Tool:
    name: str
    description: str
    parameters:dict[str, object]
    handler:Callable[[dict], dict | ToolResult]
    risk_level: str = "low"     # "low" | "medium" | "high"；默认低风险（只读）




if __name__ == "__main__":
    to_dict = ToolResult("成功", {}, invocation="None").to_dict()
    import json
    print(to_dict)
    print(json.dumps(to_dict))
