"""互动插件配置（对应 .env 中的 INTERACTION_* 项）。"""

from pydantic import BaseModel, Field

# 混合类型：str 表示 Unicode emoji，int 表示 QQ face ID
ReactionValue = str | int


class InteractionConfig(BaseModel):
    poke_enabled: bool = Field(
        default=True,
        description="是否启用戳一戳互动（被戳时戳回去）。",
    )
    keyword_enabled: bool = Field(
        default=True,
        description="是否启用关键词互动（匹配关键词时回复随机表情）。",
    )
    keywords: list[str] = Field(
        default=[
            "在吗",
            "在不在",
            "你好",
            "hi",
            "hello",
            "晚安",
            "早安",
            "午安",
            "安",
            "早上好",
            "晚上好",
            "下午好",
        ],
        description="关键词列表，匹配时回复随机表情。",
    )
    reactions: list[ReactionValue] = Field(
        default=["😊", "😄", "🥰", "😎", "🤗", "✨", "💕", "🌟", "🎉", "😇", "🤭", "😜", "👻", "👋", "💖"],
        description="反应列表：字符串为 Unicode emoji，整数为 QQ face ID（如 1、5、178）。从其中随机选择回复。",
    )
