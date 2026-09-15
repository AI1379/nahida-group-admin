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
from pydantic import BaseModel, Field, field_validator, model_validator

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


# 运算符别名 → 规范符号（统一用 + - × 三种）
_OPERATOR_ALIASES: dict[str, str] = {
    "+": "+",
    "＋": "+",
    "add": "+",
    "加": "+",
    "-": "-",
    "－": "-",
    "sub": "-",
    "减": "-",
    "×": "×",
    "*": "×",
    "x": "×",
    "X": "×",
    "mul": "×",
    "乘": "×",
}


class VerificationConfig(BaseModel):
    """入群人机验证（加减法等简单算术题，未通过则踢出）。"""

    enabled: bool = Field(default=True, description="是否启用入群人机验证。")
    timeout_seconds: int = Field(default=120, description="答题时限（秒）。", ge=5)
    max_attempts: int = Field(
        default=3, description="最大答题次数，超出即判定失败。", ge=1
    )
    operators: list[str] = Field(
        default_factory=lambda: ["+", "-"],
        description="出题使用的运算符：+ - ×（也接受 add/sub/mul 等别名）。",
    )
    number_min: int = Field(default=1, description="运算数下限（含）。", ge=0)
    number_max: int = Field(default=20, description="运算数上限（含）。", ge=1)
    verify_invite: bool = Field(
        default=True, description="被成员/管理员邀请入群时是否同样验证。"
    )
    kick_on_fail: bool = Field(
        default=True, description="超时或答错次数用尽时是否自动踢出。"
    )
    reject_add_request: bool = Field(
        default=False, description="踢出时是否同时拒绝其再次加群申请。"
    )
    require_bot_admin: bool = Field(
        default=True, description="机器人无管理员权限时跳过验证（否则无法踢人）。"
    )
    recall_on_pass: bool = Field(
        default=True, description="验证通过后撤回题目、答错提示与对方的回复。"
    )
    recall_on_fail: bool = Field(
        default=False, description="超时/答错用尽（判定失败）时是否也撤回上述消息。"
    )
    welcome_message: str = Field(
        default="✅ 验证通过，欢迎加入本群～",
        description="验证通过后的群内提示，留空则不发送。",
    )

    @field_validator("operators", mode="before")
    @classmethod
    def _normalize_operators(cls, value: object) -> object:
        """把运算符别名统一成 + - ×，并拒绝无法识别的写法。"""
        if not isinstance(value, list):
            return value
        normalized: list[str] = []
        for item in value:
            symbol = _OPERATOR_ALIASES.get(str(item).strip())
            if symbol is None:
                raise ValueError(f"不支持的运算符 {item!r}，仅支持 + - ×（及 add/sub/mul 别名）。")
            if symbol not in normalized:
                normalized.append(symbol)
        return normalized

    @model_validator(mode="after")
    def _check_config(self) -> "VerificationConfig":
        """校验运算符非空与运算区间。"""
        if not self.operators:
            raise ValueError("operators 不能为空，至少配置一个运算符（+ - ×）。")
        if self.number_min > self.number_max:
            raise ValueError(
                f"number_min({self.number_min}) 不能大于 number_max({self.number_max})。"
            )
        return self


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
    verification: VerificationConfig = Field(default_factory=VerificationConfig)


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
