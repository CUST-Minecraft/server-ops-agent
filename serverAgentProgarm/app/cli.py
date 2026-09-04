"""serveragent 主 CLI：操作员的唯一门面。"""
from datetime import datetime, timezone
from uuid import uuid4

import typer

from app import setup_logging

app = typer.Typer(help="ServerOpsAgent -- 智能服务器监测与自动运维 Agent")


def _authenticate_cli_user(username: str, password: str):
    """通过用户名和密码取得 CLI chat 的可信用户身份。"""
    from app.security.auth import verify_password
    from app.storage.db import SessionLocal
    from app.storage.models import User

    with SessionLocal() as session:
        user = session.query(User).filter(User.username == username).first()
        if user is None or not verify_password(password, user.password_hash):
            return None
        return user


def _persist_cli_chat(session_id: str, user_id: int, user_input: str, answer: str) -> None:
    """将一轮 CLI 对话以同一会话和用户归属写入数据库。"""
    from app.storage.db import SessionLocal
    from app.storage.models import ChatMessage

    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        session.add(ChatMessage(
            session_id=session_id,
            user_id=user_id,
            role="user",
            content=user_input,
            created_at=now,
        ))
        session.add(ChatMessage(
            session_id=session_id,
            user_id=user_id,
            role="assistant",
            content=answer,
            created_at=datetime.now(timezone.utc),
        ))
        session.commit()


@app.command()
def run():
    """启动自治闭环（监控 -> 检测 -> 调查 -> 审批 -> 修复 -> 验证）"""
    setup_logging()
    from app.runtime.runner import run as runner_run
    runner_run()


@app.command()
def status():
    """最新快照 + 最近工单 + 待审批数的一屏摘要"""
    setup_logging()
    from app.storage.db import SessionLocal, init_db
    from app.storage.models import ApprovalRequest, Incident, MetricSnapshot
    init_db()
    with SessionLocal() as s:
        snap = s.query(MetricSnapshot).order_by(MetricSnapshot.id.desc()).first()
        inc = s.query(Incident).order_by(Incident.id.desc()).first()
        pending = s.query(ApprovalRequest).filter_by(status="pending").count()
    if snap:
        print(f"最近快照(#{snap.id}): cpu={snap.cpu_used_pct}% mem={snap.mem_used_pct}% "
              f"disk={snap.disk_used_pct}% services={snap.services_status}")
    if inc:
        print(f"最近工单: #{inc.id} [{inc.status}] {inc.title}")
    print(f"待审批: {pending} 张")


@app.command()
def incidents(n: int = typer.Argument(10)):
    """显示最近 N 张工单"""
    setup_logging()
    # 已给（复用 demo/incidents.py 的查询逻辑，迁入此处）
    from app.storage.db import SessionLocal, init_db
    from app.storage.models import Incident
    init_db()
    with SessionLocal() as s:
        for i in s.query(Incident).order_by(Incident.id.desc()).limit(n)[::-1]:
            print(f"#{i.id} [{i.status:10s}] {i.title}  opened={i.opened_at} "
                  f"resolved={i.resolved_at}")


@app.command()
def approvals():
    """显示待审批的操作"""
    # 复用 ApprovalManager.list_pending()，逐条打印
    #   id / tool / args / reason / expires_at（对照 Day 7 CLI 的输出格式）
    setup_logging()
    from app.runtime_deps import build_executor_and_approvals

    _, _, approval = build_executor_and_approvals()
    reps = approval.list_pending()
    if not reps:
        print("无待审批表")
        return
    for r in reps:
        print(f"#{r.id}  {r.status.upper():8s} {r.tool}  {r.args}")
        print(f"     理由: {r.reason}")
        print(f"     有效期至: {r.expires_at}")


@app.command()
def approve(approval_id: int):
    """批准一张审批单并自动执行"""
    setup_logging()
    from app.runtime_deps import build_executor_and_approvals

    _, _, approval = build_executor_and_approvals()
    print(approval.approve(approval_id))


@app.command()
def reject(approval_id: int):
    """驳回一张审批单"""
    setup_logging()
    from app.runtime_deps import build_executor_and_approvals

    _, _, approval = build_executor_and_approvals()
    print(approval.reject(approval_id))


@app.command()
def chat():
    """与 Agent 手动对话（诊断/问答入口）"""
    setup_logging()
    from app.storage.db import init_db
    from app.runtime_deps import build_executor_and_approvals
    from app.agent.loop import run_agent
    from app.llm.llm_client import LLMClient
    from app.agent.system_prompt import get_system_prompt, update_context
    from app.agent.memory import load_memories
    from app.config import ServerSettings

    init_db()
    username = typer.prompt("用户名").strip()
    password = typer.prompt("密码", hide_input=True)
    user = _authenticate_cli_user(username, password)
    if user is None:
        typer.echo("用户名或密码错误")
        raise typer.Exit(code=1)

    session_id = f"cli_{uuid4().hex}"

    # 已给：对话循环与 Day 3 demo/agent_chat 相同，装配换 runtime_deps
    executor, registry, approval = build_executor_and_approvals()
    llm = LLMClient()
    settings = ServerSettings()
    context = {}

    messages = [{"role": "system",
                  "content": get_system_prompt(update_context(context, [], registry, settings))}]
    print(f"ServerOpsAgent 已就绪，当前用户：{user.username}（输入 q 退出）。"
          "试试：服务器资源状况如何？")

    while True:
        user_input = input("->")
        if user_input.strip() in ["q" , "quit" , "exit"]:
            break
        messages.append({"role": "user", "content": user_input})
        # 记忆正文注入当前 turn（索引只在启动时进 SYSTEM，会话内新信息靠上下文承载）
        memories = load_memories(messages)
        if memories:
            messages[-1] = {**messages[-1],
                            "content": f"[相关记忆]\n{memories}\n\n{messages[-1]['content']}"}
        answer = run_agent(llm,executor,registry,messages,context={})
        print(answer)
        _persist_cli_chat(session_id, user.id, user_input, answer)


if __name__ == "__main__":
    app()
