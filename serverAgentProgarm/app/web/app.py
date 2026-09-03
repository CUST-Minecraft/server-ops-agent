"""ServerOpsAgent Web 门面（后端半边）：JSON API。与 CLI 共享同一套领域逻辑。"""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.storage.db import SessionLocal, init_db
from app.storage.models import ApprovalRequest, ChatMessage, Incident, MetricSnapshot

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    init_db()          # 与 CLI 同款：入口即建表
    yield


app = FastAPI(title="ServerOpsAgent", lifespan=_lifespan)


def _to_dict(obj) -> dict:
    """ORM 模型 -> JSON 可序列化 dict（FastAPI 不能直接返回 SQLAlchemy 对象）。"""
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


@app.get("/api/status")
def api_status():
    with SessionLocal() as s:
        snap = s.query(MetricSnapshot).order_by(MetricSnapshot.id.desc()).first()
        inc = s.query(Incident).order_by(Incident.id.desc()).first()
        pending = s.query(ApprovalRequest).filter_by(status="pending").count()
    return {"snap": _to_dict(snap) if snap else None,
            "latest": _to_dict(inc) if inc else None,
            "pending": pending}


@app.get("/api/incidents")
def api_incidents():
    # 最近 20 张工单，detail 不返回（契约 §1.2：详情单独走 /api/incidents/{id}）
    with SessionLocal() as session:
        incidents = session.query(Incident).order_by(Incident.id.desc()).limit(20).all()
    out = []
    for inc in incidents:
        d = _to_dict(inc)
        d.pop("detail", None)
        out.append(d)
    return {"incidents": out}


@app.get("/api/approvals")
def api_approvals():
    # 待审批清单（契约 §1.3）：只挑前端需要的字段，args 原样透传
    with SessionLocal() as s:
        rows = (s.query(ApprovalRequest)
                .filter_by(status="pending")
                .order_by(ApprovalRequest.id)
                .all())
    return {"reqs": [{
        "id": r.id, "tool": r.tool, "args": r.args,
        "reason": r.reason, "status": r.status,
        "created_at": r.created_at, "expires_at": r.expires_at,
    } for r in rows]}



@app.post("/api/approvals/{approval_id}/approve")
def approve_action(approval_id: int):
      from app.runtime_deps import build_executor_and_approvals
      _, _, approvals = build_executor_and_approvals()
      msg = approvals.approve(approval_id, actor="web")   # 返回字符串（与 CLI 相同）
      return {"ok": True, "message": msg}



@app.post("/api/approvals/{approval_id}/reject")
def reject_action(approval_id: int):
    from app.runtime_deps import build_executor_and_approvals
    _, _, approvals = build_executor_and_approvals()
    msg = approvals.reject(approval_id, actor="web")  # 返回字符串（与 CLI 相同）
    return {"ok": True, "message": msg}


@app.get("/api/incidents/{incident_id}")
def api_incident_detail(incident_id: int):
    with SessionLocal() as s:
        inc = s.get(Incident, incident_id)
        if inc is None:
            raise HTTPException(404, "单子不存在")
        detail = inc.detail or {}
    return {"inc": _to_dict(inc),
            "history": detail.get("investigation_history", []),   # 每次调查（含重试）
            "notes": detail.get("notes", [])}


def _persist_chat(session_id: str, user_input: str, answer: str) -> None:
    """落库：本轮 user 输入 + assistant 回答各一条。失败只 warning，不阻塞对话。"""
    try:
        with SessionLocal() as s:
            now = datetime.now()
            s.add(ChatMessage(session_id=session_id, role="user",
                              content=user_input, created_at=now))
            s.add(ChatMessage(session_id=session_id, role="assistant",
                              content=answer, created_at=datetime.now()))
            s.commit()
    except Exception as e:
        logger.warning("chat 落库失败（不阻塞对话）: %s", e)


@app.post("/api/chat/stream")
async def chat_stream(request: Request):
    """SSE 流式：逐块推送 Agent 回复。假流式——run_agent 拿到完整回答后切块吐。"""
    from app.agent.loop import run_agent
    from app.agent.memory import load_memories
    from app.agent.system_prompt import get_system_prompt, update_context
    from app.config import ServerSettings
    from app.llm.llm_client import LLMClient
    from app.runtime_deps import build_executor_and_approvals

    data = await request.json()
    session_id = data.get("session_id", "")
    incoming = data.get("messages", [])
    user_input = incoming[-1]["content"] if incoming else ""

    async def event_stream():
        try:
            # 组装（同 CLI chat）：system + 注入记忆；压缩/提取由 run_agent 的 context 路径跑
            settings = ServerSettings()
            executor, registry, _ = build_executor_and_approvals()
            llm = LLMClient()
            system_prompt = get_system_prompt(update_context({}, [], registry, settings))
            messages = [{"role": "system", "content": system_prompt}] + incoming
            memories = load_memories(messages)
            if memories:
                for i in range(len(messages) - 1, -1, -1):
                    if messages[i].get("role") == "user":
                        messages[i] = {**messages[i],
                                       "content": f"[相关记忆]\n{memories}\n\n{messages[i]['content']}"}
                        break
            # run_agent 同步阻塞，扔线程池跑，别卡 event loop
            answer = await asyncio.to_thread(
                run_agent, llm, executor, registry, messages, context={})
            # 假流式：把最终回答切块吐给前端（打字机效果）
            for i in range(0, len(answer), 24):
                yield f"data: {json.dumps({'content': answer[i:i+24]}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.03)
            yield "data: [DONE]\n\n"
            # 落库：user 输入 + assistant 回答各一条（失败只 warning）
            await asyncio.to_thread(_persist_chat, session_id, user_input, answer)
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/chat/messages")
def chat_messages(session_id: str):
    """恢复会话历史：按 session_id 查 chat_messages，返回 user/assistant 文本序列。"""
    with SessionLocal() as s:
        rows = (s.query(ChatMessage)
                .filter_by(session_id=session_id)
                .order_by(ChatMessage.created_at, ChatMessage.id)
                .all())
    return {"messages": [{"role": r.role, "content": r.content} for r in rows]}





STATIC_DIR = Path(__file__).resolve().parents[2] / "static"

app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

