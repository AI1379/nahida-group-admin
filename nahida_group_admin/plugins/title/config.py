"""自助头衔插件配置（对应 .env 中的 TITLE_* 项）。"""

from pydantic import BaseModel, Field


class TitleConfig(BaseModel):
    title_max_length: int = Field(
        default=6,
        description="头衔最大长度（字符数）。QQ 实际上限约 18 字节（约 6 个汉字）。",
    )
    title_cooldown: int = Field(
        default=3600,
        description="同一成员两次修改之间的冷却时间（秒）；0 表示不限制。",
    )
    title_blacklist: list[str] = Field(
        default_factory=list,
        description="禁止出现在头衔中的子串列表。",
    )
