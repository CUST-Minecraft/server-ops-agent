"""最小审批入口。用法：
  python -m app.approval_cli list
  python -m app.approval_cli show 1
  python -m app.approval_cli approve 1
  python -m app.approval_cli reject 1
"""
import sys

from app import setup_logging
from app.storage.db import SessionLocal, init_db


def main() -> None:
    setup_logging()
    init_db()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    from app.runtime_deps import build_executor_and_approvals   # 见下：装配函数抽出

    if cmd in ("list", "show"):
        _, _, approvals = build_executor_and_approvals()
        reqs = approvals.list_pending()
        if not reqs:
            print("（没有待审批的操作）")
            return
        for r in reqs:
            print(f"#{r.id}  {r.status.upper():8s} {r.tool}  {r.args}")
            print(f"     理由: {r.reason}")
            print(f"     过期于: {r.expires_at}")
        if cmd == "show" and len(sys.argv) > 2:
            req = next((r for r in reqs if r.id == int(sys.argv[2])), None)
            print("详情:", req.args, req.created_at)
    elif cmd == "approve" and len(sys.argv) > 2:
        _, _, approvals = build_executor_and_approvals()
        print(approvals.approve(int(sys.argv[2])))
    elif cmd == "reject" and len(sys.argv) > 2:
        _, _, approvals = build_executor_and_approvals()
        print(approvals.reject(int(sys.argv[2])))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()