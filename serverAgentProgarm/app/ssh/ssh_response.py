from typing import TypedDict


class SshResponse(TypedDict):
    cmd: str # 执行的命令
    exit_code:int # 退出码
    stdout:str # 响应结果
    stderr:str # 错误结果
    elapsed:int # 回复时间