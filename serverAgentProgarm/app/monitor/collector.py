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

        resource_results = {
            "get_cpu_status": {},
            "get_memory_usage": {},
            "get_disk_usage": {},
        }
        for name, args in resource_results.items():     # 资源段已给
            r = self.executor.execute(name, args)
            if r.status != "success":
                raise RuntimeError(f"采集 {name} 失败: {r.error}（本轮快照作废）")
            snap.update(r.data)

        # TODO(你来实现) 服务状态段：
        #   对 self.services 逐个 execute("get_service_status", {"service": svc})
        #   - 成功：services_status[svc] = r.data["state"]
        #   - 失败（非 success）：services_status[svc] = "unknown"，**不抛异常继续**
        #     （为什么与资源段区别对待，见下方解释）
        #   最后 snap["services_status"] = services_status

        server_status_tools = {
            "get_service_status":  [service for service in self.services],
        }
        service_status = {}
        for service_name,args_list in server_status_tools.items():
            for args in args_list:
                r = self.executor.execute(service_name,{"service":args})
                if r.status != "success":
                    service_status[args] = "unknown"
                    logger.warning("采集 %s 状态失败: %s", args, r.error)
                else:
                    service_status[args] = r.data["state"]
        snap["services_status"] = service_status
        return snap