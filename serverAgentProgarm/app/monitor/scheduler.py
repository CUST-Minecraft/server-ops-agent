"""巡检调度器：采集 -> 落盘 -> 休息，周而复始。Day 5 将在此插入检测环节。"""
import logging
import time

from app import setup_logging
from app.agent.executor import ToolExecutor
from app.config import ServerSettings , ThresholdSettings
from app.monitor.collector import Collector
from app.ssh.ssh_client import SSHClient
from app.storage.db import SessionLocal, init_db
from app.storage.models import MetricSnapshot
from app.tools.builtin import build_readonly_tools
from app.tools.registry import ToolRegistry
from app.detect.rules import build_rules
from app.detect.detector import Detector
from app.detect.incident_service import IncidentService

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
    rules_settings = ThresholdSettings()
    rule = build_rules(rules_settings)
    init_db()
    collector = build_collector()

    services = [s.strip() for s in settings.watched_services.split(",") if s.strip()]
    incident_service = IncidentService(SessionLocal)
    detector = Detector(rules=rule, service_sustain=rules_settings.service_sustain, watched_services=services,open_kinds=incident_service.find_open_kind_set())


    logger.info("巡检启动 interval=%ss services=%s", settings.monitor_interval,
                settings.watched_services)
    while True:
        try:
            snap = collector.collect()
            with SessionLocal() as session:
                metric_snapshot = MetricSnapshot(
                    collected_at = snap["collected_at"],
                    cpu_used_pct=snap["cpu_used_pct"],
                    load_1m=snap["load_1m"],
                    load_5m=snap["load_5m"],
                    load_15m=snap["load_15m"],
                    mem_used_pct=snap["mem_used_pct"],
                    mem_available_mb=snap["mem_available_mb"],
                    disk_used_pct=snap["disk_used_pct"],
                    services_status=snap["services_status"]

                )
                session.add(metric_snapshot)
                session.commit()


            logger.info("快照入库 cpu=%.1f%% mem=%.1f%% disk=%.1f%% services=%s",
                        snap["cpu_used_pct"], snap["mem_used_pct"], snap["disk_used_pct"],
                        snap["services_status"])
            events = detector.check(snap)
            if events:
                incident_service.apply(events)
                logger.warning(msg=f"检测到事件:{events}")

        except Exception:                      # noqa: BLE001  长驻进程不许死
            logger.exception("本轮巡检失败（进程继续运行）")
        time.sleep(settings.monitor_interval)


if __name__ == "__main__":
    run()