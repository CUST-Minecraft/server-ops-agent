"""手动执行一个 Runbook 的演示入口。用法：
  uv run python demo/run_runbook.py nginx_restart
（默认按 .env 的 POLICY_MODE 走权限链；建议先设 POLICY_MODE=auto 演示直通）
"""
import sys

from app import setup_logging
from app.remediation.runbooks import RUNBOOKS
from app.remediation.service import RemediationService
from app.remediation.verifier import Verifier
from app.runtime_deps import build_executor_and_approvals
from app.storage.db import SessionLocal, init_db

if __name__ == "__main__":
    setup_logging()
    init_db()
    rb = next((r for r in RUNBOOKS if r.name == sys.argv[1]), None)
    if rb is None:
        print(f"未知预案。可用: {[r.name for r in RUNBOOKS]}"); sys.exit(1)

    executor, registry, _ = build_executor_and_approvals()
    service = RemediationService(SessionLocal, executor, Verifier(executor))
    print(f"执行预案 {rb.name}: {rb.plan}")
    print("最终状态:", service.execute_runbook(rb))
