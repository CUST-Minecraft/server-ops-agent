"""Day 3 演示：第一个可对话的运维 Agent。"""
from app import setup_logging, ServerSettings
from app.agent.executor import ToolExecutor
from app.agent.loop import SYSTEM_PROMPT, run_agent
from app.llm.llm_client import LLMClient
from app.runtime_deps import build_executor_and_approvals
from app.security.approval import ApprovalManager
from app.security.policy import PermissionEngine
from app.ssh.ssh_client import SSHClient
from app.storage.db import SessionLocal, init_db
from app.tools.builtin import build_readonly_tools
from app.tools.registry import ToolRegistry
from app.tools.remediation import build_remediation_tools


def build_agent() -> tuple:
    """装配：依赖在根上创建一次，逐层传递。"""
    init_db()
    executor, registry, approvals = build_executor_and_approvals()
    return LLMClient(), executor, registry, approvals


if __name__ == "__main__":
    setup_logging()
    llm, executor, registry, approvals = build_agent()          # 装配已给：顺序即依赖顺序
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    print("ServerOpsAgent 已就绪（输入 q 退出）。试试：服务器资源状况如何？")
    #   while True:
    #     input 读入 -> q/quit/exit 退出 -> 空输入跳过
    #     -> messages.append({"role": "user", "content": ...})
    #     -> answer = run_agent(llm, executor, registry, messages) -> 打印

    while True:
        user_input = input()
        if user_input in ["q" , "quit" , "exit"]:
            break
        messages.append({"role": "user", "content": user_input})
        answer = run_agent(llm,executor,registry,messages)
        print(answer)