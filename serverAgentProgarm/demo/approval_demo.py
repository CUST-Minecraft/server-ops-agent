# 临时脚本（跑完删）：不起 LLM，直接测管理器
from app.agent.executor import ToolExecutor
from app.security.approval import ApprovalManager
from app.security.policy import PermissionEngine
from app.storage.db import SessionLocal, init_db
from app.tools.base import Tool
from app.tools.registry import ToolRegistry

init_db()
r = ToolRegistry()
r.register(Tool(name="fake_write", description="x",
                parameters={"type": "object", "properties": {}},
                handler=lambda a: {"done": True}, risk_level="medium"))
ex = ToolExecutor(r, policy=PermissionEngine("standard"), session_factory=SessionLocal)
am = ApprovalManager(SessionLocal, ex, ttl_minutes=60)

req = am.create_pending("fake_write", {"k": 1}, "测试挂起")
for r in am.list_pending():             # 循环打印字段，而不是 print 整个列表
    print(f"#{r.id}  {r.status}  {r.tool}  {r.args}")
print(am.approve(req.id))              # 应执行 fake_write 并返回 success 摘要
print(am.approve(req.id))              # 应报"已处理"，不再执行