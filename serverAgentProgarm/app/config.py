from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8",extra="ignore")

    server_host: str
    server_port: int = Field(default=22, ge=1, le=65535)
    server_user: str
    key_path : str
    db_url: str
    log_level: str
    monitor_interval: int = 30          # MONITOR_INTERVAL，秒
    watched_services: str = "ssh,docker"  # WATCHED_SERVICES，逗号分隔

class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )
    api_key: SecretStr
    base_url: str
    model_id: str



if __name__ == "__main__":
    s = ServerSettings()
    model = LLMSettings()
    print(model)
    print(f"目标服务器: {s.server_user}@{s.server_host}:{s.server_port}")
    print(f"数据库: {s.db_url}")
    print(f"key_path路径: {s.key_path}")
    print(s.server_host)


