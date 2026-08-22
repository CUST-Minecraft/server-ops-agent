"""巡检调度器：采集 -> 落盘 -> 休息，周而复始。Day 5 将在此插入检测环节。"""
import logging
import time

from app import setup_logging
from app.agent.executor import ToolExecutor
from app.config import ServerSettings
from app.monitor.collector import Collector
from app.ssh.ssh_client import SSHClient
from app.storage.db import SessionLocal, init_db
from app.storage.models import MetricSnapshot
from app.tools.builtin import build_readonly_tools
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def build_collector() -> Collector:
    """装配采集链：SSH -> 工具 -> Registry -> Executor -> Collector。"""
    settings = ServerSettings()
    ssh = SSHClient()
    registry = ToolRegistry()
    for tool in build_readonly_tools(ssh):
        registry.register(tool)
    services = [s.strip() for s in settings.watched_services.split(",") if s.strip()]
    return Collector(ToolExecutor(registry), services)


def run() -> None:
    setup_logging()
    settings = ServerSettings()
    init_db()
    collector = build_collector()
    logger.info("巡检启动 interval=%ss services=%s", settings.monitor_interval,
                settings.watched_services)
    while True:
        try:
            snap = collector.collect()
            # TODO(你来实现) 入库：
            #   with SessionLocal() as session:
            #       逐字段构造 MetricSnapshot(...)...（8 个字段从 snap 取，
            #       collected_at 是 datetime 对象，直接传 snap["collected_at"]）
            #       session.add(...) + session.commit()
            logger.info("快照入库 cpu=%.1f%% mem=%.1f%% disk=%.1f%% services=%s",
                        snap["cpu_used_pct"], snap["mem_used_pct"], snap["disk_used_pct"],
                        snap["services_status"])
        except Exception:                      # noqa: BLE001  长驻进程不许死
            logger.exception("本轮巡检失败（进程继续运行）")
        time.sleep(settings.monitor_interval)


if __name__ == "__main__":
    run()