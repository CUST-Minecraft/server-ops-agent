"""公共夹具：离线测试环境（内存库 / Fake SSH / Fake LLM）。"""
import os

os.environ.update({
    "SERVER_HOST": "test-host",
    "SERVER_USER": "test-user",
    "KEY_PATH": "C:/test/key",
    "DB_URL": "sqlite+pysqlite://",
    "LOG_LEVEL": "INFO",
    "API_KEY": "test-key",
    "BASE_URL": "https://llm.invalid",
    "MODEL_ID": "test-model",
})

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent.executor import ToolExecutor
from app.security.approval import ApprovalManager
from app.security.policy import PermissionEngine
from app.storage.models import Base
from app.tools.builtin import build_readonly_tools
from app.tools.registry import ToolRegistry


class FakeSSHClient:
    """按命令片段返回预置响应，并记录所有调用。"""

    def __init__(self, outputs: dict[str, str | dict] | None = None):
        self.outputs = outputs or {}
        self.commands: list[str] = []

    def run(self, cmd: str) -> dict:
        self.commands.append(cmd)
        response = {"cmd": cmd, "exit_code": 0, "stdout": "", "stderr": "", "elapsed": 1}
        for pattern, output in self.outputs.items():
            if pattern in cmd:
                if isinstance(output, dict):
                    response.update(output)
                else:
                    response["stdout"] = output
                break
        return response


class FakeLLM:
    """脚本化 LLM：每次 chat 按顺序返回 tool_calls 或最终文本。"""

    def __init__(self, script: list[tuple[str, object]]):
        self.script = script
        self.calls = 0

    def chat(self, messages, tools=None):
        kind, payload = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1

        class ToolCall:
            pass

        class Message:
            pass

        class Choice:
            pass

        class Response:
            pass

        message = Message()
        choice = Choice()
        if kind == "tool_calls":
            message.content = "我先查一下"
            message.tool_calls = []
            for name, args_json, call_id in payload:
                call = ToolCall()
                call.id = call_id
                call.function = ToolCall()
                call.function.name = name
                call.function.arguments = args_json
                message.tool_calls.append(call)
            choice.finish_reason = "tool_calls"
        else:
            message.content = payload
            message.tool_calls = None
            choice.finish_reason = "stop"
        choice.message = message
        response = Response()
        response.choices = [choice]
        return response


@pytest.fixture()
def db(monkeypatch):
    """每个用例独占共享连接的 SQLite 内存库，不碰 MySQL。"""
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)

    import app.security.auth as auth
    import app.storage.db as storage_db
    import app.web.app as web_app

    monkeypatch.setattr(storage_db, "engine", engine)
    monkeypatch.setattr(storage_db, "SessionLocal", sessions)
    monkeypatch.setattr(auth, "SessionLocal", sessions)
    monkeypatch.setattr(web_app, "SessionLocal", sessions)
    yield sessions
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def fake_ssh():
    return FakeSSHClient({
        "top -bn1": "Cpu(s):  5.0%us,  0.0%sy,  95.0 id\nload average: 0.20, 0.10, 0.05",
        "free -m": "Mem:           1795        1123         102          12         570         512",
        "df -h": "/dev/sda1 100G 25G 75G 25% /",
    })


@pytest.fixture()
def registry(fake_ssh):
    result = ToolRegistry()
    for tool in build_readonly_tools(fake_ssh):
        result.register(tool)
    return result


@pytest.fixture()
def executor(registry, db):
    return ToolExecutor(registry, policy=PermissionEngine("standard"), session_factory=db)


@pytest.fixture()
def approvals(executor, db):
    result = ApprovalManager(db, executor)
    executor.approval_manager = result
    return result


@pytest.fixture()
def memory_dir(tmp_path, monkeypatch):
    import app.agent.memory as memory

    path = tmp_path / ".memory"
    monkeypatch.setattr(memory, "MEMORY_DIR", path)
    return path
