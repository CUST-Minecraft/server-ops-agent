"""查看最近 N 条巡检快照（默认 10）。用法：uv run python demo/latest_snapshots.py [N]"""
import sys

from app.storage.db import SessionLocal, init_db
from app.storage.models import MetricSnapshot


def main(n: int = 10) -> None:
    init_db()
    with SessionLocal() as session:
        rows = (session.query(MetricSnapshot)
                .order_by(MetricSnapshot.collected_at.desc())
                .limit(n).all())[::-1]           # 反转成时间正序
    for r in rows:
        print(f"{r.collected_at}  cpu={r.cpu_used_pct:5.1f}%  "
              f"mem={r.mem_used_pct:5.1f}%  disk={r.disk_used_pct:3.0f}%  "
              f"services={r.services_status}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)