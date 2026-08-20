from app.ssh.ssh_client import SSHClient
from app.tools.builtin import build_readonly_tools
from app.tools.registry import ToolRegistry
from app.agent.executor import ToolExecutor

r = ToolRegistry()
for t in build_readonly_tools(SSHClient()): r.register(t)
ex = ToolExecutor(r)

print(ex.execute("get_cpu_status"))                      # 期望: success
print(ex.execute("get_disk_usage", {"path": "不合法"}))   # 期望: error（校验异常被捕获，进程不崩）
print(ex.execute("不存在的工具"))                          # 期望: error（未知工具）