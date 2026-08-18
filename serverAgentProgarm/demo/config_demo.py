"""Day 1 示例：Pydantic Settings 最小可运行写法。

运行前提：pip install pydantic-s
运行方式：在同目录放 .env 文件后  python example/config_demo.py
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """项目配置：字段即类型契约，启动即校验。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    server_host: str
    server_port: int = Field(default=22, ge=1, le=65535)
    server_user: str = "opsagent"

    db_url: str
    log_level: str = "INFO"


if __name__ == "__main__":
    s = Settings()
    print(f"目标服务器: {s.server_user}@{s.server_host}:{s.server_port}")
    print(f"数据库: {s.db_url}")

    # 体会一下"启动即校验"：把 .env 里 SERVER_PORT 改成 99999 再跑，
    # 程序会在第一行之前就抛出 ValidationError，而不是运行到一半才崩。
