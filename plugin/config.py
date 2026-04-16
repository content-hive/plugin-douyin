"""Douyin plugin configuration schema."""

from pydantic import Field
from contenthive.plugins.contracts import PluginConfigSchema


class ConfigSchema(PluginConfigSchema):
    cookies: str = Field(
        default="",
        title="Cookies",
        description="抖音账号的 Cookie 字符串，用于访问需要登录的内容",
        json_schema_extra={"secret": True},
    )
    download_max_retries: int = Field(
        default=3,
        title="最大重试次数",
        description="下载失败时的最大重试次数",
    )


CONFIG_SCHEMA = ConfigSchema
