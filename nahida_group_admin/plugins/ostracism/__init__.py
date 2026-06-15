"""陶片放逐：借鉴古雅典「陶片放逐制」的群内投票踢人机制。

- 管理员发起投票，指定要放逐的人
- 群成员对 bot 发出的通知消息贴「表情回应」投票（群表情回应功能）
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
  2. Bot 发送投票通知，注明需贴的表情回应
  3. 成员对该通知消息贴「表情回应」参与投票（群表情回应功能）
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
        f"请对本条消息贴 {vote_emoji_display} 表情回应参与投票！"
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

    await ostracism_cmd.finish(f"已发起陶片放逐投票，请对通知消息贴 {vote_emoji_display} 表情回应投票～")


# 监听通知事件，检测「表情回应」投票（NapCat/LLOneBot 扩展：group_msg_emoji_like）
from nonebot import on_notice

vote_notice = on_notice(block=False)

# NapCat 群消息表情回应事件的 notice_type
_EMOJI_LIKE_NOTICE_TYPE = "group_msg_emoji_like"


@vote_notice.handle()
async def handle_reaction_vote(bot: Bot, event) -> None:  # noqa: ANN001 - NoneBot 依赖注入
    """处理表情回应投票：成员对通知消息贴投票表情即记一票。"""
    if not config.enabled:
        return

    # 仅处理群消息表情回应事件（NoneBot 适配器无该模型，会回退为基类 NoticeEvent）
    if getattr(event, "notice_type", None) != _EMOJI_LIKE_NOTICE_TYPE:
        return

    message_id = getattr(event, "message_id", None)
    session = _active_sessions.get(message_id)
    if not session:
        return

    # 会话超时则清理
    if session.is_expired():
        _active_sessions.pop(message_id, None)
        return

    reactor_id = getattr(event, "user_id", None)
    reacted_emoji_id = str(getattr(event, "emoji_id", ""))

    # 首次收到时打印原始字段，便于在真实 NapCat 上核对 emoji_id 格式
    logger.debug(
        f"收到表情回应：msg={message_id} user={reactor_id} "
        f"emoji_id={reacted_emoji_id!r}（期望 {str(config.vote_emoji)!r}）"
    )

    # 表情必须与配置的投票表情一致
    if reacted_emoji_id != str(config.vote_emoji):
        return

    # 目标本人不能为自己投票；同一人只计一次
    if reactor_id is None or reactor_id == session.target_user_id:
        return
    if reactor_id in session.voters:
        return

    session.voters.add(reactor_id)
    current_votes = len(session.voters)

    # 达到阈值：踢人
    if session.should_kick():
        _active_sessions.pop(message_id, None)
        try:
            await bot.call_api(
                "set_group_kick",
                group_id=session.group_id,
                user_id=session.target_user_id,
                reject_add_request=False,
            )
            await bot.send_group_msg(
                group_id=session.group_id,
                message=Message(
                    f"陶片放逐成功！{MessageSegment.at(session.target_user_id)} "
                    f"已被踢出群聊（{current_votes} 票）🏺"
                ),
            )
        except ActionFailed as e:
            logger.warning(
                f"踢人失败（group={session.group_id}, user={session.target_user_id}）：{e}"
            )
            await bot.send_group_msg(
                group_id=session.group_id,
                message=f"踢人失败：我可能没有足够权限（需管理员/群主）😢（已获得 {current_votes} 票）",
            )

