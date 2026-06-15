"""集中式配置：从独立的 ``config.yaml`` 加载，用 pydantic 校验。

放弃 NoneBot 的 dotenv 机制（``.env`` 修改后不立即生效），改为：
1. 启动时读取单一 ``config.yaml``（YAML 原生支持列表/字典，无类型歧义）；
2. 用 pydantic 模型校验并给出默认值；
3. 框架设置（driver/host/port 等）通过 ``nonebot.init(**kwargs)`` 注入；
4. 插件配置通过本模块的 ``get_config()`` 单例访问。

所有模型集中在此文件，便于维护。各插件通过 ``get_config().<section>`` 取自己的配置。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

# ── 各功能配置模型 ──

# 混合类型：str 表示 Unicode emoji，int 表示 QQ face ID
ReactionValue = str | int


class TitleConfig(BaseModel):
    """自助派发头衔。"""

    max_length: int = Field(default=6, description="头衔最大字符数。", ge=1)
    cooldown: int = Field(default=3600, description="修改冷却（秒），0 表示不限制。", ge=0)
    blacklist: list[str] = Field(
        default_factory=list, description="禁止出现在头衔中的子串。"
    )


class MuteConfig(BaseModel):
    """自助禁言。"""

    mutable_titles: list[str] = Field(
        default_factory=list, description="允许普通成员禁言的「目标头衔」列表。"
    )
    max_duration_seconds: int = Field(
        default=600, description="普通成员单次禁言的最长时长（秒）；0 表示不限制。", ge=0
    )
    admin_bypass: bool = Field(
        default=True, description="管理员/群主是否可无视「可禁言头衔」列表。"
    )


class InteractionConfig(BaseModel):
    """互动（戳一戳 + 关键词表情回应）。"""

    poke_enabled: bool = Field(default=True, description="是否启用戳一戳互动。")
    keyword_enabled: bool = Field(default=True, description="是否启用关键词互动。")
    keywords: list[str] = Field(
        default_factory=list, description="关键词列表，匹配时贴表情回应。"
    )
    reactions: list[ReactionValue] = Field(
        default_factory=list,
        description="反应列表：字符串为 Unicode emoji，整数为 QQ face ID。",
    )


class OstracismConfig(BaseModel):
    """陶片放逐。"""

    enabled: bool = Field(default=True, description="是否启用陶片放逐功能。")
    vote_emoji: ReactionValue = Field(
        default="🏺",
        description="投票表情：字符串为 Unicode emoji，整数为 QQ face ID。",
    )
    votes_fixed: int = Field(default=5, description="固定票数阈值；-1 表示不考虑。", ge=-1)
    votes_percent: int = Field(
        default=-1, description="群成员百分比阈值（1-100）；-1 表示不考虑。", ge=-1, le=100
    )
    window_minutes: int = Field(default=30, description="投票有效时间窗（分钟）。", ge=1)

    def calculate_threshold(self, group_member_count: int) -> int:
        """取「固定票数」与「百分比×成员数」的最小值；-1 表示不考虑该项。"""
        thresholds: list[int] = []
        if self.votes_fixed >= 0:
            thresholds.append(self.votes_fixed)
        if self.votes_percent >= 0:
            thresholds.append(max(1, int(group_member_count * self.votes_percent / 100)))
        if not thresholds:
            return 1
        return min(thresholds)


# ── 根配置 ──


class AppConfig(BaseModel):
    """根配置：框架设置 + 全局设置 + 各插件配置。"""

    # NoneBot 框架（通过 nonebot.init 注入）
    driver: str = "~fastapi+~httpx+~websockets"
    host: str = "127.0.0.1"
    port: int = 8080
    log_level: str = "INFO"
    command_start: list[str] = Field(default_factory=lambda: ["/"])
    superusers: list[str] = Field(default_factory=list)
    onebot_access_token: Optional[str] = None

    # 全局
    group_whitelist: list[int] = Field(
        default_factory=list, description="群聊白名单；为空表示不限制。"
    )

    # 各插件
    title: TitleConfig = Field(default_factory=TitleConfig)
    mute: MuteConfig = Field(default_factory=MuteConfig)
    interaction: InteractionConfig = Field(default_factory=InteractionConfig)
    ostracism: OstracismConfig = Field(default_factory=OstracismConfig)


# ── 加载与单例 ──

_config: Optional[AppConfig] = None
_DEFAULT_PATH = Path("config.yaml")


def load_config(path: str | Path = _DEFAULT_PATH) -> AppConfig:
    """从 YAML 文件加载并校验配置，存入模块单例。"""
    global _config
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"配置文件 {p} 不存在，请参考 config.example.yaml 创建一份。"
        )
    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    _config = AppConfig(**raw)
    return _config


def get_config() -> AppConfig:
    """获取已加载的配置单例；未加载则报错。"""
    if _config is None:
        raise RuntimeError("配置尚未加载，请先调用 load_config()。")
    return _config
