"""自助禁言插件配置（对应 .env 中的 MUTE_* 项）。"""

from pydantic import BaseModel, Field


class MuteConfig(BaseModel):
    mutable_titles: list[str] = Field(
        default_factory=list,
        description="允许普通成员禁言的「目标头衔」列表。若目标的群专属头衔在此列表中，普通成员可对其发起禁言。",
    )
    max_duration_seconds: int = Field(
        default=600,
        description="普通成员单次禁言的最长时长（秒）；0 表示不限制。",
    )
    admin_bypass: bool = Field(
        default=True,
        description="管理员/群主是否可无视「可禁言头衔」列表，禁言任意成员。",
    )
