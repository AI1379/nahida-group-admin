"""陶片放逐插件配置（对应 .env 中的 OSTRACISM_* 项）。"""

from pydantic import BaseModel, Field

# 混合类型：str 表示 Unicode emoji，int 表示 QQ face ID
ReactionValue = str | int


class OstracismConfig(BaseModel):
    enabled: bool = Field(
        default=True,
        description="是否启用陶片放逐功能。",
    )
    vote_emoji: ReactionValue = Field(
        default="🏺",
        description="投票表情：字符串为 Unicode emoji，整数为 QQ face ID（如 1、5、178）。",
    )
    votes_fixed: int = Field(
        default=5,
        description="固定票数阈值；-1 表示不考虑此项。",
        ge=-1,
    )
    votes_percent: int = Field(
        default=-1,
        description="群成员百分比阈值（1-100）；-1 表示不考虑此项。",
        ge=-1,
        le=100,
    )
    window_minutes: int = Field(
        default=30,
        description="投票有效时间窗（分钟），超时自动取消。",
        ge=1,
    )

    def calculate_threshold(self, group_member_count: int) -> int:
        """计算实际票数阈值：取「固定票数」与「百分比×成员数」的最小值（-1 表示不限制）。

        例如：
        - votes_fixed=5, votes_percent=10, 群 50 人 → min(5, 5) = 5 票
        - votes_fixed=5, votes_percent=-1, 群 50 人 → min(5, ∞) = 5 票
        - votes_fixed=-1, votes_percent=10, 群 50 人 → min(∞, 5) = 5 票
        """
        thresholds = []

        if self.votes_fixed >= 0:
            thresholds.append(self.votes_fixed)

        if self.votes_percent >= 0:
            percent_count = max(1, int(group_member_count * self.votes_percent / 100))
            thresholds.append(percent_count)

        if not thresholds:
            return 1  # 兜底：至少 1 票

        return min(thresholds)
