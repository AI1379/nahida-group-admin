"""陶片放逐：借鉴古雅典「陶片放逐制」的群内投票踢人机制。

- 管理员发起投票，指定要放逐的人
- 群成员通过回复消息并贴特定表情投票
- 达到票数阈值后自动踢出群聊
"""

import time
from dataclasses import dataclass, field
from typing import Dict, Set

from nonebot import get_driver, get_plugin_config, logger, on_command
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    Message,
    MessageEvent,
    MessageSegment,
)
from nonebot.adapters.onebot.v11.exception import ActionFailed
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from nahida_group_admin.compat import mute_group_member

from .config import OstracismConfig

__plugin_meta__ = PluginMetadata(
    name="陶片放逐 / Ostracism",
    description="借鉴古雅典「陶片放逐制」的群内投票踢人机制。Group voting to kick members via emoji reactions.",
    usage="""命令 / Commands:
  /放逐 @某人        — 发起对某人的陶片放逐投票
  /放逐 <QQ号>       — 发起对指定 QQ 号的放逐投票
  /ostracism @某人   — 同上

流程 / Process:
  1. 管理员发起投票
  2. Bot 发送投票通知，注明需贴的表情
  3. 成员回复 Bot 消息并贴投票表情参与投票
  4. 达到阈值后自动踢出

配置 / Config:
  - OSTRACISM_VOTE_EMOJI: 投票表情（支持 emoji 字符串或 QQ face ID）
  - OSTRACISM_VOTES_FIXED: 固定票数；-1 表示不考虑
  - OSTRACISM_VOTES_PERCENT: 群成员百分比；-1 表示不考虑
  - OSTRACISM_WINDOW_MINUTES: 投票有效时间（分钟）

票数计算：
  取「固定票数」与「百分比×成员数」的最小值；两者都可设 -1 忽略""",
    config=OstracismConfig,
)

config = get_plugin_config(OstracismConfig)
driver = get_driver()


@dataclass
class OstracismSession:
    """陶片放逐会话。"""

    group_id: int
    target_user_id: int
    message_id: int
    initiator_id: int
    threshold: int
    start_time: float
    voters: Set[int] = field(default_factory=set)

    def is_expired(self) -> bool:
        """检查是否超时。"""
        return time.time() - self.start_time > config.window_minutes * 60

    def should_kick(self) -> bool:
        """检查是否达到踢人阈值。"""
        return len(self.voters) >= self.threshold


# 活跃的放逐会话：{message_id: session}
_active_sessions: Dict[int, OstracismSession] = {}


def _is_admin(bot: Bot, event: GroupMessageEvent) -> bool:
    """检查用户是否为管理员（群主/管理员/超级用户）。"""
    superusers = driver.config.superusers
    if str(event.user_id) in superusers:
        return True
    sender_role = event.sender.role
    return sender_role in ("admin", "owner")


ostracism_cmd = on_command(
    "放逐",
    aliases={"ostracism", "陶片放逐", "投票踢人"},
    block=True,
)


@ostracism_cmd.handle()
async def handle_ostracism(
    bot: Bot,
    event: GroupMessageEvent,
    args: Message = CommandArg(),
) -> None:
    """处理放逐命令。"""
    if not config.enabled:
        await ostracism_cmd.finish("陶片放逐功能未启用～")

    if not _is_admin(bot, event):
        await ostracism_cmd.finish("仅管理员可发起陶片放逐投票～")

    group_id, initiator_id = event.group_id, event.user_id

    # 解析目标：@ 提及或纯 QQ 号
    at_segments = [seg for seg in args if seg.type == "at"]
    raw_text = args.extract_plain_text().strip()

    target_user_id = None

    if at_segments:
        target_user_id = int(at_segments[0].data["qq"])
    elif raw_text and raw_text.isdigit():
        target_user_id = int(raw_text)
    else:
        await ostracism_cmd.finish(
            "用法：/放逐 @某人\n或：/放逐 <QQ号>"
        )

    # 不能放逐机器人自己
    if target_user_id == bot.self_id:
        await ostracism_cmd.finish("不能放逐我！😢")

    # 不能放诉管理员/群主（可选限制）
    try:
        target_info = await bot.get_group_member_info(
            group_id=group_id, user_id=target_user_id
        )
        if target_info.get("role") in ("admin", "owner"):
            await ostracism_cmd.finish("不能放逐管理员或群主～")
    except ActionFailed:
        pass  # 获取失败时跳过检查

    # 获取群成员数并计算阈值
    try:
        member_info = await bot.get_group_member_info(group_id=group_id, user_id=bot.self_id)
        group_member_count = member_info.get("member_count", 0)
        if group_member_count == 0:
            # 部分协议端可能不返回 member_count，尝试获取群信息
            group_info = await bot.call_api("get_group_info", group_id=group_id)
            group_member_count = group_info.get("member_count", 0)
    except ActionFailed:
        group_member_count = 0  # 获取失败时兜底

    threshold = config.calculate_threshold(group_member_count)

    # 发送投票通知
    vote_emoji_display = (
        MessageSegment.face(config.vote_emoji)
        if isinstance(config.vote_emoji, int)
        else config.vote_emoji
    )

    # 构建阈值说明
    threshold_desc = f"{threshold} 票"
    if config.votes_fixed >= 0 and config.votes_percent >= 0:
        threshold_desc = f"min({config.votes_fixed}, {config.votes_percent}%×{group_member_count}) = {threshold} 票"
    elif config.votes_percent >= 0:
        threshold_desc = f"{config.votes_percent}%×{group_member_count} = {threshold} 票"

    notification = Message(
        f"【陶片放逐投票】\n"
        f"目标：{MessageSegment.at(target_user_id)}\n"
        f"发起人：{MessageSegment.at(initiator_id)}\n"
        f"所需票数：{threshold_desc}\n"
        f"有效时间：{config.window_minutes} 分钟\n\n"
        f"请回复本消息并贴 {vote_emoji_display} 表情投票！"
    )

    try:
        msg = await bot.send(event, notification)
        message_id = msg["message_id"]
    except ActionFailed as e:
        logger.warning(f"发送投票通知失败：{e}")
        await ostracism_cmd.finish("发送投票通知失败，请检查权限～")
        return

    # 创建会话
    session = OstracismSession(
        group_id=group_id,
        target_user_id=target_user_id,
        message_id=message_id,
        initiator_id=initiator_id,
        start_time=time.time(),
        threshold=threshold,
    )
    _active_sessions[message_id] = session

    await ostracism_cmd.finish(f"已发起陶片放逐投票，请回复投票通知并贴 {vote_emoji_display} 表情～")


# 监听消息，检测投票
from nonebot import on_message

vote_handler = on_message(block=False)


@vote_handler.handle()
async def handle_vote(bot: Bot, event: GroupMessageEvent) -> None:
    """处理投票消息。"""
    if not config.enabled:
        return

    # 检查是否为回复消息
    reply = event.reply
    if not reply:
        return

    reply_message_id = reply.message_id

    # 检查是否为对放逐通知的回复
    session = _active_sessions.get(reply_message_id)
    if not session:
        return

    # 检查会话是否超时
    if session.is_expired():
        del _active_sessions[reply_message_id]
        return

    # 检查是否为同一群
    if event.group_id != session.group_id:
        return

    # 检查是否已投过票
    if event.user_id in session.voters:
        return

    # 不能重复投给自己
    if event.user_id == session.target_user_id:
        return

    # 检查消息是否包含投票表情
    has_vote_emoji = False
    if isinstance(config.vote_emoji, int):
        # QQ face ID：检查是否有对应 face 段
        has_vote_emoji = any(
            seg.type == "face" and int(seg.data.get("id", 0)) == config.vote_emoji
            for seg in event.get_message()
        )
    else:
        # Unicode emoji：检查文本是否包含
        has_vote_emoji = config.vote_emoji in event.get_plaintext()

    if not has_vote_emoji:
        return

    # 记录投票
    session.voters.add(event.user_id)
    current_votes = len(session.voters)

    # 检查是否达到阈值
    if session.should_kick():
        # 移除会话
        del _active_sessions[reply_message_id]

        # 踢人
        try:
            # 使用禁言 API 的特殊形式：duration = 0 表示移出群？
            # 实际上 OneBot V11 没有 "kick" API，需要用 set_group_kick
            await bot.call_api(
                "set_group_kick",
                group_id=session.group_id,
                user_id=session.target_user_id,
                reject_add_request=False,
            )

            await bot.send(
                event,
                f"陶片放逐成功！{MessageSegment.at(session.target_user_id)} 已被踢出群聊（{current_votes} 票）🏺",
            )
        except ActionFailed as e:
            logger.warning(f"踢人失败（group={session.group_id}, user={session.target_user_id}）：{e}")
            await bot.send(
                event,
                f"踢人失败：我可能没有足够权限（需管理员/群主）😢（已获得 {current_votes} 票）",
            )
    else:
        # 更新投票进度（可选：回复提示）
        remaining = session.threshold - current_votes
        if remaining <= 3:  # 接近阈值时提示
            try:
                await bot.send(
                    event,
                    f"当前票数：{current_votes}/{session.threshold}，还需 {remaining} 票",
                )
            except ActionFailed:
                pass
