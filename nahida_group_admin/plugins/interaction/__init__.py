"""互动功能：戳一戳回应 + 关键词表情回应。

- 戳一戳：被戳时戳回去
- 关键词：匹配关键词时对这条消息贴「表情回应」（群表情回应，而非回复一条表情消息）
"""

import random

from nonebot import on_notice, logger, on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent, MessageSegment
from nonebot.adapters.onebot.v11.event import PokeNotifyEvent
from nonebot.plugin import PluginMetadata

from nahida_group_admin.compat import react_to_message
from nahida_group_admin.config import InteractionConfig, get_config

__plugin_meta__ = PluginMetadata(
    name="互动 / Interaction",
    description="戳一戳回应与关键词表情回应。Poke back when poked, react with emoji on keywords.",
    usage="""功能 / Features:
  - 戳一戳回应：被戳时自动戳回去
  - 关键词互动：消息包含关键词时，对该消息贴「表情回应」（群表情回应）

关键词 / Keywords: 在吗、在不在、你好、晚安、早安、午安 等
表情 / Reactions: 从配置列表随机选择（支持 Unicode emoji 或 QQ face ID）""",
    config=InteractionConfig,
)

config = get_config().interaction

# ── 戳一戳互动 ──


poke_notice = on_notice()


@poke_notice.handle()
async def handle_poke(bot: Bot, event: PokeNotifyEvent) -> None:
    """被戳时戳回去。"""
    if not config.poke_enabled:
        return

    target_id = event.target_id
    sender_id = event.user_id
    logger.info("收到戳一戳事件")

    # 只在机器人被戳时回应
    if str(target_id) != str(bot.self_id):
        return

    logger.info("被戳对象为 Bot")

    # 群聊戳回去
    try:
        await bot.call_api(
            "group_poke",
            group_id=int(event.group_id),
            user_id=sender_id,
        )
    except Exception:
        logger.warning("群聊戳一戳 API 调用失败")


# ── 关键词互动 ──


keyword_msg = on_message(block=False)


@keyword_msg.handle()
async def handle_message(
    bot: Bot,
    event: GroupMessageEvent | MessageEvent,
) -> None:
    """消息处理：包含关键词时对该消息贴「表情回应」。"""
    if not config.keyword_enabled:
        return

    text = event.get_plaintext().strip().lower()

    # 检查是否包含关键词
    if not any(kw in text for kw in config.keywords):
        return

    # 随机选择反应（str 为 Unicode emoji，int 为 QQ face ID）
    reaction = random.choice(config.reactions)

    group_id = getattr(event, "group_id", None)
    message_id = getattr(event, "message_id", None)

    # 群聊：贴表情回应；私聊（无 group_id）或不支持时，回退为发送表情消息
    if group_id is not None and message_id is not None:
        try:
            await react_to_message(
                bot, group_id=group_id, message_id=message_id, emoji=reaction
            )
            return
        except Exception as e:
            logger.warning(
                f"贴表情回应失败，回退为发送表情消息 | "
                f"msg_id={message_id} group={group_id} emoji={reaction!r} "
                f"err={type(e).__name__}: {e}"
            )

    # 回退：直接发送表情
    if isinstance(reaction, int):
        await bot.send(event, MessageSegment.face(reaction))
    else:
        await bot.send(event, reaction)
