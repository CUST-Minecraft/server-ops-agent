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
    policy_mode: str = "standard"
    approval_ttl_minutes: int = 60 # 默认审批时间
    investigate_max_retries: int = 2
    alert_webhook_url : str | None = None
    max_output_chars :int = 8000
    memory_consolidate_threshold: int = 10    # 记忆文件数达到此值触发整理（步骤7）
    compact_token_threshold: int = 24000      # 估算 token 超此值触发 L4 摘要（Day14 步骤1）

class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )
    api_key: SecretStr
    base_url: str
    model_id: str

class ThresholdSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8",
                                      env_prefix="THRESHOLD_", extra="ignore")
    cpu_pct: float = 85
    mem_pct: float = 85
    disk_pct: float = 80
    sustain: int = 3
    service_sustain: int = 2

if __name__ == "__main__":
    s = ServerSettings()
    model = LLMSettings()
    print(model)
    print(f"目标服务器: {s.server_user}@{s.server_host}:{s.server_port}")
    print(f"数据库: {s.db_url}")
    print(f"key_path路径: {s.key_path}")
    print(s.server_host)


