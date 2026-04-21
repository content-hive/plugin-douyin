"""Douyin plugin configuration schema."""

from pydantic import Field
from contenthive.plugins.contracts import PluginConfigSchema


class ConfigSchema(PluginConfigSchema):
    cookies: str = Field(
        default="",
        title="凭证",
        description="必填。抖音账号的 Cookie 字符串，用于获取抖音的内容",
        json_schema_extra={"secret": True},
    )
    download_max_retries: int = Field(
        default=3,
        title="下载重试次数",
        description="下载失败时的重试次数",
    )


CONFIG_SCHEMA = ConfigSchema
