"""ServerOpsAgent Web 门面（后端半边）：JSON API。与 CLI 共享同一套领域逻辑。"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.storage.db import SessionLocal, init_db
from app.storage.models import ApprovalRequest, Incident, MetricSnapshot


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


STATIC_DIR = Path(__file__).resolve().parents[2] / "static"

app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

