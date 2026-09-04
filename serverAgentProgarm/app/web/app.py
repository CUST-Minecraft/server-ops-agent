"""ServerOpsAgent Web 门面（后端半边）：JSON API。与 CLI 共享同一套领域逻辑。"""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request,Depends
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from app.security.auth import verify_password, create_token, get_current_user
from app.storage.db import  init_db
from app.storage.models import ApprovalRequest, ChatMessage, Incident, MetricSnapshot, User
import hashlib
from datetime import datetime, timezone
from fastapi import Header, HTTPException
from app.storage.db import SessionLocal
from app.storage.models import AuthToken

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    init_db()          # 与 CLI 同款：入口即建表
    yield


app = FastAPI(title="ServerOpsAgent", lifespan=_lifespan)

WEB_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; base-uri 'self'; connect-src 'self'; "
        "font-src 'self'; form-action 'self'; frame-ancestors 'none'; "
        "img-src 'self' data:; object-src 'none'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline'"
    ),
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
    "Referrer-Policy": "same-origin",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


@app.middleware("http")
async def add_web_security_headers(request: Request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith(("/docs", "/redoc")):
        for header, value in WEB_SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
    return response


def _to_dict(obj) -> dict:
    """ORM 模型 -> JSON 可序列化 dict（FastAPI 不能直接返回 SQLAlchemy 对象）。"""
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


@app.get("/api/status")
def api_status(current_user: User = Depends(get_current_user)):
    with SessionLocal() as s:
        snap = s.query(MetricSnapshot).order_by(MetricSnapshot.id.desc()).first()
        inc = s.query(Incident).order_by(Incident.id.desc()).first()
        pending = s.query(ApprovalRequest).filter_by(status="pending").count()
    return {"snap": _to_dict(snap) if snap else None,
            "latest": _to_dict(inc) if inc else None,
            "pending": pending}


@app.get("/api/incidents")
def api_incidents(current_user: User = Depends(get_current_user)):
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
def api_approvals(current_user: User = Depends(get_current_user)):
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
def approve_action(approval_id: int, current_user: User = Depends(get_current_user)):
    from app.runtime_deps import build_executor_and_approvals

    _, _, approvals = build_executor_and_approvals()
    msg = approvals.approve(approval_id, actor=current_user.username)
    return {"ok": True, "message": msg}



@app.post("/api/approvals/{approval_id}/reject")
def reject_action(approval_id: int, current_user: User = Depends(get_current_user)):
    from app.runtime_deps import build_executor_and_approvals

    _, _, approvals = build_executor_and_approvals()
    msg = approvals.reject(approval_id, actor=current_user.username)
    return {"ok": True, "message": msg}


@app.get("/api/incidents/{incident_id}")
def api_incident_detail(incident_id: int, current_user: User = Depends(get_current_user)):
    with SessionLocal() as s:
        inc = s.get(Incident, incident_id)
        if inc is None:
            raise HTTPException(404, "单子不存在")
        detail = inc.detail or {}
    return {"inc": _to_dict(inc),
            "history": detail.get("investigation_history", []),   # 每次调查（含重试）
            "notes": detail.get("notes", [])}


from pydantic import BaseModel

# 定义登录数据
class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/auth/login")
def login(data: LoginRequest):
    with SessionLocal() as session:
        user = (
            session.query(User)
            .filter(User.username == data.username)
            .first()
        )
        if user is None or not verify_password(
            data.password,
            user.password_hash
        ):
            raise HTTPException(
                status_code=401,
                detail="用户名或密码错误",
            )
        token = create_token(user_id=user.id)
        return {
            "token":token
        }



@app.post("/api/auth/logout")
def logout(authorization: str | None = Header(default=None),):
    # 1. 检查请求头
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")

    # 2. 取出原始 Token
    token = authorization.removeprefix("Bearer ").strip()

    if not token:
        raise HTTPException(status_code=401, detail="Token 不能为空")
    # 3. 计算 Token 哈希
    token_hash = hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

    # 4. 查找并注销 Token
    with SessionLocal() as session:
        auth_token = (
            session.query(AuthToken)
            .filter(AuthToken.token_hash == token_hash)
            .first()
        )

        if auth_token is None:
            raise HTTPException(status_code=401, detail="Token 无效")

        auth_token.revoked_at = datetime.now(timezone.utc)
        session.commit()

    # 5. 返回前端需要的格式
    return {"ok": True}


def _persist_chat(session_id: str,user_id:int,user_input: str, answer: str) -> None:
    """落库：本轮 user 输入 + assistant 回答各一条。失败只 warning，不阻塞对话。"""
    try:
        with SessionLocal() as s:
            now = datetime.now()
            s.add(ChatMessage(session_id=session_id, user_id=user_id,role="user",
                              content=user_input, created_at=now))
            s.add(ChatMessage(session_id=session_id,user_id=user_id,role="assistant",
                              content=answer, created_at=datetime.now()))
            s.commit()
    except Exception as e:
        logger.warning("chat 落库失败（不阻塞对话）: %s", e)


@app.post("/api/chat/stream")
async def chat_stream(request: Request,current_user: User = Depends(get_current_user)):
    """SSE 流式：逐块推送 Agent 回复。假流式——run_agent 拿到完整回答后切块吐。"""
    from app.agent.loop import run_agent
    from app.agent.memory import load_memories
    from app.agent.system_prompt import get_system_prompt, update_context
    from app.config import ServerSettings
    from app.llm.llm_client import LLMClient
    from app.runtime_deps import build_executor_and_approvals

    data = await request.json()
    session_id = data.get("session_id", "")
    user_id = current_user.id
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
            await asyncio.to_thread(_persist_chat, session_id,user_id,user_input, answer)
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/chat/messages")
def api_chat_messages(session_id: str, current_user: User = Depends(get_current_user)):
    with SessionLocal() as s:
        # 第一次：只根据 session_id 查归属
        owner_message = (
            s.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id)
            .first()
        )
        if owner_message is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        if owner_message.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权访问该会话")
        # 第二次：确认归属后，再查消息
        rows = (
            s.query(ChatMessage)
            .filter(
                ChatMessage.session_id == session_id,
                ChatMessage.user_id == current_user.id,
            )
            .order_by(ChatMessage.created_at, ChatMessage.id)
            .all()
        )
    return {
        "messages": [
            {"role": row.role, "content": row.content}
            for row in rows
        ]
    }





STATIC_DIR = Path(__file__).resolve().parents[2] / "static"

app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

