import time
import paramiko
from paramiko import SSHException
from app.ssh.ssh_response import SshResponse
from app.config import ServerSettings


def _init_ssh_client(settings:ServerSettings):
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=settings.server_host,
            port=settings.server_port,
            username=settings.server_user,
            key_filename=settings.key_path,
            timeout=10,
        )
        return client
    except paramiko.SSHException:
        raise SSHException("SSH connection failed")


class SSHClient:
    def __init__(self):
        self.settings = ServerSettings()
        self.client = _init_ssh_client(self.settings)

    def _reconnect(self) -> None:
        """重建连接。连接失败抛异常（由调用方决定降级）。"""
        #重新 self._init_ssh_client(self.settings)
        try:
            self.client.close()
        except Exception:
            pass
        try:
            self.client = _init_ssh_client(self.settings)
        except SSHException as e:
            raise SSHException("SSH reconnection failed.output:{e}".format(e=e))

    def run(self, cmd: str) -> SshResponse:
        #   1) transport = self.client.get_transport()
        #      若 transport 为 None 或 not transport.is_active() -> self._reconnect()
        #   2) 正常执行原逻辑
        #   3) except paramiko.SSHException: 先 _reconnect() 再执行一次（重试恰好一次）
        #      仍失败 -> 抛出（保持 Day 1 的"连接类故障抛异常"约定）
        transport = self.client.get_transport()
        if transport is None or not transport.is_active():
            self._reconnect()
        try:
            return self._get_cmd(cmd)
        except SSHException:
            try:
                self._reconnect()
                return self._get_cmd(cmd)
            except SSHException as e:
                raise SSHException(f"SSH run command failed.output:{e}")

    def _get_cmd(self,cmd: str) -> SshResponse:
        start = time.monotonic()
        _, stdout, stderr = self.client.exec_command(cmd, timeout=10)
        exit_code = stdout.channel.recv_exit_status()
        elapsed = int((time.monotonic() - start) * 1000)
        cmd_result = stdout.read().decode().strip()  # 拿到命令执行结果
        cmd_err = stderr.read().decode().strip()  # 拿到错误结果
        return {
            "cmd": cmd,
            "exit_code": exit_code,
            "stdout": cmd_result,
            "stderr": cmd_err,
            "elapsed": elapsed
        }

if __name__ == "__main__":
    client = SSHClient()
    response:SshResponse = client.run("uptime && ls ~")
    print(response)




