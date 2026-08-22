"""采集器：复用 Day 2 只读工具，产出一次同时刻快照。"""
import logging
from datetime import datetime, timezone
from app.agent.executor import ToolExecutor
logger = logging.getLogger(__name__)


class Collector:
    def __init__(self, executor: ToolExecutor, services: list[str]):
        self.executor = executor
        self.services = services

    def collect(self) -> dict:
        """一次采集 = 一次同时刻快照。任一资源指标失败即抛异常（本轮放弃，不落半张快照）。"""
        snap: dict = {"collected_at": datetime.now(timezone.utc)}
        r = self.executor.execute("get_cpu_status", {})
        if r.status != "success":
            raise RuntimeError(f"采集 get_cpu_status 失败: {r.error}（本轮快照作废）")
        snap.update(r.data)                       # cpu 的 4 字段全局唯一，可整体摊平

        r = self.executor.execute("get_memory_usage", {})
        if r.status != "success":
            raise RuntimeError(f"采集 get_memory_usage 失败: {r.error}（本轮快照作废）")
        snap["mem_used_pct"] = r.data["used_pct"]              # ← 挑字段 + 改名，对齐表列
        snap["mem_available_mb"] = r.data["available_mb"]

        r = self.executor.execute("get_disk_usage", {})
        if r.status != "success":
            raise RuntimeError(f"采集 get_disk_usage 失败: {r.error}（本轮快照作废）")
        snap["disk_used_pct"] = r.data["used_pct"]

        #   对 self.services 逐个 execute("get_service_status", {"service": svc})
        #   - 成功：services_status[svc] = r.data["state"]
        #   - 失败（非 success）：services_status[svc] = "unknown"，**不抛异常继续**
        #     （为什么与资源段区别对待，见下方解释）
        # 因为服务查询本来就会有失败的可能性, 但是资源如果失败了, 那证明这个服务端本身就无法运行
        #   最后 snap["services_status"] = services_status

        server_status = {}
        for service in self.services:
            r = self.executor.execute("get_service_status", {"service": service})
            if r.status != "success":
                server_status[service] = "unknown"
                logger.warning("采集 %s 状态失败: %s", service, r.error)
            else:
                server_status[service] = r.data["state"]
        snap["services_status"] = server_status

        return snap