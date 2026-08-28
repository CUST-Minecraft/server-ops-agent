"""告警通道：Incident 开/关单时主动通知。console 必达；webhook 可选。"""
import logging

import requests   # 领域素材：唯一的新依赖；若不想引入可用 urllib（见注意）

logger = logging.getLogger(__name__)


class Alerter:
    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url

    def incident_opened(self, incident) -> None:
        self._send(f"🔔 [ALERT] Incident #{incident.id} 已开启: {incident.title} "
                   f"(severity={incident.severity})")

    def incident_resolved(self, incident) -> None:
        self._send(f"✅ [ALERT] Incident #{incident.id} 已解决: {incident.title}")

    def _send(self, text: str) -> None:
        print(text)                                   # console 通道：永远执行
        if not self.webhook_url:
            return
        # TODO(你来实现) webhook 通道：
        #   requests.post(self.webhook_url, json={"text": text}, timeout=5)
        #   失败只记 error 日志，绝不抛异常（告警失败不能影响值班主流程）
        try:
            requests.post(self.webhook_url, json={"text": text}, timeout=5)
        except Exception as e:
            logger.error(f"通知失败:{e}")
