"""互动功能：戳一戳回应 + 关键词表情回复。

- 戳一戳：被戳时戳回去
- 关键词：匹配关键词时回复随机表情
"""

import random

from nonebot import get_plugin_config, on_command, on_notice
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent
from nonebot.adapters.onebot.v11.event import PokeNotifyEvent
from nonebot.plugin import PluginMetadata

from .config import InteractionConfig

__plugin_meta__ = PluginMetadata(
    name="互动 / Interaction",
    description="戳一戳回应与关键词表情回复。Poke back when poked, reply with emoji on keywords.",
    usage="""功能 / Features:
  - 戳一戳回应：被戳时自动戳回去
  - 关键词互动：消息包含关键词时回复随机表情

关键词 / Keywords: 在吗、在不在、你好、晚安、早安、午安、 Evening 等
表情 / Emojis: 随机从预设列表中选择""",
    config=InteractionConfig,
)

config = get_plugin_config(InteractionConfig)

# ── 戳一戳互动 ──


poke_notice = on_notice()


@poke_notice.handle()
async def handle_poke(bot: Bot, event: PokeNotifyEvent) -> None:
    """被戳时戳回去。"""
    if not config.poke_enabled:
        return

    target_id = event.target_id
    sender_id = event.user_id

    # 只在机器人被戳时回应
    if target_id != bot.self_id:
        return

    # 群聊戳回去
    try:
        await bot.call_api(
            "group_poke",
            group_id=int(event.group_id),
            user_id=sender_id,
        )
    except Exception:
        pass  # 失败时忽略


# ── 关键词互动 ──


from nonebot import on_message

keyword_msg = on_message(block=False)


@keyword_msg.handle()
async def handle_message(
    bot: Bot,
    event: GroupMessageEvent | MessageEvent,
) -> None:
    """消息处理：包含关键词时回复随机表情。"""
    if not config.keyword_enabled:
        return

    text = event.get_plaintext().strip().lower()

    # 检查是否包含关键词
    if not any(kw in text for kw in config.keywords):
        return

    # 随机选择反应
    reaction = random.choice(config.reactions)

    # 区分类型：str 是 Unicode emoji，int 是 QQ face ID
    if isinstance(reaction, int):
        await bot.send(event, MessageSegment.face(reaction))
    else:
        await bot.send(event, reaction)
