"""完整 Agent→Executor→MCP→observation→Agent 闭环，使用真实 stdio 和脚本模型。"""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sys

# 此验收脚本不读取真实 .env，不使用 SSH、远端模型或业务数据库。
os.environ.update({"SERVER_HOST":"fixture.invalid", "SERVER_USER":"fixture",
    "KEY_PATH":"fixture-key-unused", "DB_URL":"sqlite+pysqlite://", "LOG_LEVEL":"WARNING",
    "API_KEY":"fixture-unused", "BASE_URL":"https://fixture.invalid", "MODEL_ID":"fixture"})
from app.config import ServerSettings, LLMSettings
ServerSettings.model_config["env_file"] = None
LLMSettings.model_config["env_file"] = None

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.agent.executor import ToolExecutor
from app.agent.loop import run_agent
from app.security.policy import PermissionEngine
from app.storage.models import Base, AuditLog
from app.tools.mcp import register_mcp_tools
from app.tools.registry import ToolRegistry

ROOT = Path(__file__).resolve().parents[1]
ALIAS = "mcp_dbdiag_get_db_connections"
# 固定已审查契约；不是在每次启动时无条件信任最新 tools/list。
FIXTURE_CONTRACT = "12714968680579a2384f3a0a565b74c8102971ac65a2f62bd30f090804d2f00c"


class ScriptedModel:
    """只模拟模型协议，第二轮回答严格读取真实 MCP observation。"""
    def __init__(self): self.round = 0

    def chat(self, messages, tools=None):
        self.round += 1
        if self.round == 1:
            assert any(tool["function"]["name"] == ALIAS for tool in tools)
            print("1. 脚本模型提出工具调用：数据库 shop，id=mcp-demo-call-1")
            call = SimpleNamespace(id="mcp-demo-call-1", function=SimpleNamespace(
                name=ALIAS, arguments=json.dumps({"database":"shop"})))
            message = SimpleNamespace(content="先查询连接数。",tool_calls=[call])
            reason = "tool_calls"
        else:
            observation = next(item for item in messages if item.get("tool_call_id")=="mcp-demo-call-1")
            body=json.loads(observation["content"])
            assert body["status"]=="success" and body["data"]["source"]["transport"]=="mcp"
            payload=body["data"]["payload"]
            print("2. 原 Loop 回填 MCP 观察：" + json.dumps(body,ensure_ascii=False))
            content=(f"教学数据库连接数为 {payload['active_connections']}/{payload['max_connections']}，"
                     "占比 90%。数据来自 fixture；真实故障仍需查询实际数据库。")
            message=SimpleNamespace(content=content,tool_calls=None)
            reason="stop"
        return SimpleNamespace(choices=[SimpleNamespace(message=message,finish_reason=reason)])


def main():
    print("本地验收：真实 SDK/子进程/原 Agent Loop；脚本模型，无 LLM 请求。")
    engine=create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine)
    config={"version":1,"servers":[{"id":"dbdiag","transport":"stdio",
        "command":sys.executable,"args":[str(ROOT/"demo/mcp_dbdiag_server.py")],
        "cwd":str(ROOT),"env_vars":[],"timeout_seconds":10,"tools":[{
            "remote_name":"get_db_connections","local_name":ALIAS,"description":"只读查询教学连接数",
            "risk_level":"low","expected_contract_sha256":FIXTURE_CONTRACT,
            "allowed_arguments":{"database":["shop","empty"]}}]}]}
    registry=ToolRegistry()
    try:
        with TemporaryDirectory(prefix="serveragent-mcp-") as temporary:
            path=Path(temporary)/"mcp.json"
            path.write_text(json.dumps(config,ensure_ascii=False),encoding="utf-8")
            registered=register_mcp_tools(registry,SimpleNamespace(mcp_enabled=True,
                mcp_config_path=str(path),max_output_chars=8000))
            assert registered==[ALIAS]
            executor=ToolExecutor(registry,PermissionEngine(),session_factory=sessions)
            messages=[{"role":"user","content":"查询 shop 数据库连接数"}]
            answer=run_agent(ScriptedModel(),executor,registry,messages)
            print("3. 模型第二轮根据工具结果回答："+answer)
            with sessions() as session:
                audits=session.query(AuditLog).filter_by(tool=ALIAS).count()
            assert audits==1
            print("4. 权限审计：1 条；所有 MCP 上下文已退出。")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
