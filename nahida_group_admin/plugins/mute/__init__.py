"""自助禁言：群成员在规则约束下对特定成员发起禁言。

典型场景：允许普通成员禁言挂着特定头衔（如 "bot"）的机器人小号。
"""

import re

from nonebot import get_driver, logger, on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment
from nonebot.adapters.onebot.v11.exception import ActionFailed
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from nahida_group_admin.compat import mute_group_member
from nahida_group_admin.config import MuteConfig, get_config

__plugin_meta__ = PluginMetadata(
    name="自助禁言 / Self-Service Mute",
    description="群成员在规则约束下对特定成员发起禁言。Members can mute specific members under rule constraints.",
    usage="""命令 / Commands:
  /mute @某人 <时长>  — 禁言某人（时长支持 5m/30s/1h 格式）
  /禁言 @某人 <时长>  — 同上

时长格式 / Duration format: 5m（5分钟）、30s（30秒）、1h（1小时）

限制 / Limits:
  - 普通成员只能禁言「头衔在可禁言列表中」的成员
  - 普通成员受单次最长时长限制
  - 管理员可无视规则（可配置）""",
    config=MuteConfig,
)

config = get_config().mute
driver = get_driver()

_DURATION_PATTERN = re.compile(r"(\d+)([smh])", re.IGNORECASE)
_DURATION_UNITS = {"s": 1, "m": 60, "h": 3600}


def _is_admin(bot: Bot, event: GroupMessageEvent) -> bool:
    """检查用户是否为管理员（群主/管理员/超级用户）。"""
    superusers = driver.config.superusers
    if str(event.user_id) in superusers:
        return True
    sender_role = event.sender.role
    return sender_role in ("admin", "owner")


def _parse_duration(text: str) -> int | None:
    """解析时长文本（如 5m、30s、1h），返回秒数；解析失败返回 None。"""
    match = _DURATION_PATTERN.fullmatch(text.strip())
    if not match:
        return None
    amount, unit = match.groups()
    return int(amount) * _DURATION_UNITS[unit.lower()]


mute_cmd = on_command(
    "禁言",
    aliases={"mute", "封禁", "禁", "踢", "禁言"},
    block=True,
)


@mute_cmd.handle()
async def handle_mute(
    bot: Bot,
    event: GroupMessageEvent,
    args: Message = CommandArg(),
) -> None:
    group_id, user_id = event.group_id, event.user_id
    is_admin = _is_admin(bot, event)

    # 解析 @ 提及和时长
    at_segments = [seg for seg in args if seg.type == "at"]
    if not at_segments:
        await mute_cmd.finish("用法：/禁言 @某人 <时长>\n时长格式：5m（5分钟）、30s（30秒）、1h（1小时）")

    target_user_id = int(at_segments[0].data["qq"])
    duration_text = args.extract_plain_text().strip()

    if not duration_text:
        await mute_cmd.finish("请提供禁言时长，如：/禁言 @某人 5m")

    duration_seconds = _parse_duration(duration_text)
    if duration_seconds is None:
        await mute_cmd.finish(
            "时长格式不正确，应为：5m（5分钟）、30s（30秒）、1h（1小时）"
        )

    # 若非管理员，需获取目标的头衔并检查是否在可禁言列表中
    can_bypass = is_admin and config.admin_bypass
    target_title = None

    if not can_bypass:
        try:
            member_info = await bot.get_group_member_info(
                group_id=group_id, user_id=target_user_id
            )
            target_title = member_info.get("card") or member_info.get("nickname", "")
        except ActionFailed as e:
            logger.warning(f"获取成员信息失败（group={group_id}, user={target_user_id}）：{e}")
            await mute_cmd.finish("获取成员信息失败，无法确认是否可禁言～")

        if target_title not in config.mutable_titles:
            await mute_cmd.finish(
                f"对方的头衔「{target_title}」不在可禁言列表中，你无法禁言此人～"
            )

        # 检查时长限制
        if (
            config.max_duration_seconds > 0
            and duration_seconds > config.max_duration_seconds
        ):
            max_m = config.max_duration_seconds // 60
            await mute_cmd.finish(
                f"普通成员单次禁言最多 {max_m} 分钟，请缩短时长～"
            )

    # 执行禁言
    try:
        await mute_group_member(
            bot, group_id=group_id, user_id=target_user_id, duration=duration_seconds
        )
    except ActionFailed as e:
        logger.warning(f"禁言失败（group={group_id}, user={target_user_id}）：{e}")
        await mute_cmd.finish("禁言失败：我可能没有足够权限（需管理员/群主）😢")
    except NotImplementedError:
        await mute_cmd.finish("当前后端暂不支持禁言～")

    # 回执
    duration_display = duration_text
    await mute_cmd.finish(
        Message(
            f"已将 {MessageSegment.at(target_user_id)} 禁言 {duration_display} 🤐"
        )
    )
