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

class Incident(Base):
    """一次异常事件（工单）。状态机：open -> resolved（Day 8/9 将扩展中间状态）。"""
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(index=True)     # 规则 key 或 "service_down:<name>"
    severity: Mapped[str]                             # warning / critical
    status: Mapped[str] = mapped_column(default="open")   # open / resolved（后续扩展）
    title: Mapped[str]                                # 人话标题
    detail: Mapped[dict] = mapped_column(JSON, default=dict)  # 开单时的事实快照
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class AuditLog(Base):
    """工具调用决策审计：每一次经过权限闸门的调用一条记录。"""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    tool: Mapped[str]
    args: Mapped[dict] = mapped_column(JSON, default=dict)
    decision: Mapped[str]                      # allow / needs_approval / deny
    reason: Mapped[str]
    status: Mapped[str] = mapped_column(default="decided")   # decided / executed（Day 7 补）
    incident_id: Mapped[int | None] = mapped_column(nullable=True)  # Day 9 关联工单


class ApprovalRequest(Base):
    """一张审批单 = 一次被挂起的工具调用。状态机：pending -> approved | rejected | expired。"""
    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tool: Mapped[str]
    args: Mapped[dict] = mapped_column(JSON)               # 审批时人看到的就是它
    args_hash: Mapped[str]                                  # 防篡改绑定（见步骤 2）
    reason: Mapped[str]                                     # 权限引擎给出的挂起理由
    status: Mapped[str] = mapped_column(default="pending")  # pending/approved/rejected/expired
    result_status: Mapped[str | None] = mapped_column(nullable=True)  # 执行结果（approved 后填）
    incident_id: Mapped[int | None] = mapped_column(nullable=True)    # Day 9 起关联工单
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(nullable=True)     # 审批人标识

    def __repr__(self):
        """调试友好：print / 日志里直接可读，而不是 <ApprovalRequest object at 0x...>。"""
        return (f"ApprovalRequest(id={self.id}, tool={self.tool!r}, "
                f"args={self.args!r}, status={self.status!r})")