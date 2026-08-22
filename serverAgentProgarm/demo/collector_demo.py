from app.ssh.ssh_client import SSHClient
from app.tools.builtin import build_readonly_tools
from app.tools.registry import ToolRegistry
from app.agent.executor import ToolExecutor
from app.monitor.collector import Collector

r = ToolRegistry()
for t in build_readonly_tools(SSHClient()): r.register(t)
c = Collector(ToolExecutor(r), ["ssh", "docker"])
print(c.collect())