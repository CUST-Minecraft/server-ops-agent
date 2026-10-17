"""受信任的本地 MCP 配置；不接受模型提供启动命令或凭据。"""
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
Scalar = str | bool | int | float | None


class MCPConfigError(ValueError):
    """配置错误的消息不包含输入内容或凭据。"""


class AllowedMCPTool(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)
    remote_name: str = Field(min_length=1)
    local_name: str = Field(pattern=r"^[A-Za-z0-9_]{1,64}$")
    description: str = Field(min_length=1)
    risk_level: Literal["low"]
    expected_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    allowed_arguments: dict[str, tuple[Scalar, ...]] = Field(default_factory=dict)

    @field_validator("allowed_arguments")
    @classmethod
    def nonempty_scopes(cls, scopes):
        if any(not name or not values for name, values in scopes.items()):
            raise ValueError("参数白名单不能为空")
        return scopes


class MCPServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)
    id: str = Field(pattern=r"^[A-Za-z0-9_]{1,32}$")
    transport: Literal["stdio"] = "stdio"
    command: str
    args: tuple[str, ...] = ()
    cwd: str
    env_vars: tuple[str, ...] = ()
    timeout_seconds: float = Field(default=10.0, gt=0, le=30)
    tools: tuple[AllowedMCPTool, ...]

    @field_validator("command")
    @classmethod
    def executable_path(cls, value):
        if not Path(value).is_absolute() or not Path(value).is_file():
            raise ValueError("command 必须是存在的绝对文件路径")
        return value

    @field_validator("cwd")
    @classmethod
    def directory_path(cls, value):
        if not Path(value).is_absolute() or not Path(value).is_dir():
            raise ValueError("cwd 必须是存在的绝对目录路径")
        return value

    @field_validator("env_vars")
    @classmethod
    def environment_names(cls, names):
        import re
        if len(names) != len(set(names)) or any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", n) for n in names):
            raise ValueError("env_vars 必须是互不重复的环境变量名")
        return names


class MCPConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)
    version: Literal[1] = 1
    servers: tuple[MCPServerConfig, ...]

    @model_validator(mode="after")
    def unique_names(self):
        ids = [server.id for server in self.servers]
        aliases = [tool.local_name for server in self.servers for tool in server.tools]
        if len(ids) != len(set(ids)) or len(aliases) != len(set(aliases)):
            raise ValueError("Server id 和本地工具别名必须唯一")
        return self


def resolve_config_path(path: str | Path) -> Path:
    result = Path(path)
    return result if result.is_absolute() else PROJECT_ROOT / result


def load_mcp_config(path: str | Path) -> MCPConfig:
    try:
        text = resolve_config_path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        raise MCPConfigError("无法读取 MCP 配置文件") from None
    try:
        return MCPConfig.model_validate_json(text)
    except ValidationError as error:
        # 不使用 str(error)：里面可能包含用户配置的秘密。
        locations = {".".join(str(part) for part in item["loc"])
                     for item in error.errors(include_input=False, include_context=False)}
        raise MCPConfigError("MCP 配置不合法：" + ", ".join(sorted(locations))) from None
