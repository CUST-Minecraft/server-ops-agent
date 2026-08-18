import time
import paramiko
from paramiko import SSHException
from app.ssh.ssh_response import SshResponse
from app.config import ServerSettings

class SSHClient:
    def __init__(self):
        self.settings = ServerSettings()
        self.client = self._init_ssh_client(self.settings)


    def _init_ssh_client(self, settings:ServerSettings):
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


    def run(self,cmd:str)->SshResponse:
        try:
            start = time.monotonic()
            _, stdout, stderr = self.client.exec_command(cmd,timeout=10)
            exit_code = stdout.channel.recv_exit_status()
            elapsed = int((time.monotonic() - start) * 1000)
            cmd_result = stdout.read().decode().strip() # 拿到命令执行结果
            cmd_err = stderr.read().decode().strip() # 拿到错误结果
            return {
                "cmd": cmd,
                "exit_code": exit_code,
                "stdout": cmd_result,
                "stderr": cmd_err,
                "elapsed": elapsed
            }
        except paramiko.SSHException as e:
            raise SSHException(f"SSH run command failed.output:{e}")

if __name__ == "__main__":
    client = SSHClient()
    response:SshResponse = client.run("cd /home/misaka && ls")
    print(response)




