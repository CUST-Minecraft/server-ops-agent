"""所有数据表定义。随课程天数逐步增加（今天只有快照表）。"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class MetricSnapshot(Base):
    """一次巡检快照：同一时刻的资源指标与服务状态。"""
    __tablename__ = "metric_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    cpu_used_pct: Mapped[float]
    load_1m: Mapped[float]
    load_5m: Mapped[float]
    load_15m: Mapped[float]
    mem_used_pct: Mapped[float]
    mem_available_mb: Mapped[float]
    disk_used_pct: Mapped[float]
    services_status: Mapped[dict] = mapped_column(JSON, default=dict)