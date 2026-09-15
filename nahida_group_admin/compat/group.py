"""跨适配器的群管理能力门面。

NoneBot 统一了事件分发与运行生命周期，但不同适配器暴露的「动作 API」在名称与参数上
并不一致。本模块把上层功能所需的群管理操作，收敛成一组与适配器无关的函数，内部再按
Bot 的具体类型分发到对应适配器的调用。

当前以 OneBot V11 为主实现；Milky 为次要路径，部分动作名 / 参数仍需与
``nonebot-adapter-milky`` 源码核对（见各处 TODO）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from nonebot.adapters.onebot.v11 import Bot as OneBotV11Bot

if TYPE_CHECKING:
    from nonebot.adapters import Bot


def _milky_bot_cls():
    """返回 Milky 的 Bot 类；未安装适配器时返回 None。"""
    try:
        from nonebot.adapters.milky import Bot as MilkyBot
    except ImportError:
        return None
    return MilkyBot


def _extract_message_id(result: Any) -> int | None:
    """从协议端返回中取出消息 ID：OneBot 用 ``message_id``，Milky 用 ``message_seq``。

    后端未返回可用 ID 时返回 ``None``（调用方需兼容，例如放弃撤回）。
    """
    if isinstance(result, dict):
        for key in ("message_id", "message_seq"):
            value = result.get(key)
            if value is not None:
                return int(value)
    return None


async def set_special_title(
    bot: "Bot", *, group_id: int, user_id: int, title: str
) -> None:
    """设置群成员的专属头衔；``title`` 为空字符串表示清除头衔。

    注意：QQ 仅允许「群主」设置成员专属头衔，机器人需为群主，否则调用会失败
    （OneBot 端通常抛出 ActionFailed）。
    """
    if isinstance(bot, OneBotV11Bot):
        await bot.set_group_special_title(
            group_id=int(group_id),
            user_id=int(user_id),
            special_title=title,
            duration=-1,
        )
        return

    milky_cls = _milky_bot_cls()
    if milky_cls is not None and isinstance(bot, milky_cls):
        # TODO(milky): 与 nonebot-adapter-milky 源码核对动作名与参数命名。
        await bot.call_api(
            "set_group_member_special_title",
            group_id=int(group_id),
            user_id=int(user_id),
            special_title=title,
        )
        return

    raise NotImplementedError(
        f"set_special_title 暂不支持当前适配器："
        f"{type(bot).__module__}.{type(bot).__qualname__}"
    )


async def mute_group_member(
    bot: "Bot", *, group_id: int, user_id: int, duration: int
) -> None:
    """禁言群成员；``duration`` 为秒数，``0`` 表示解除禁言。

    注意：禁言权限要求视 QQ 群角色而定（管理员/群主）。
    """
    if isinstance(bot, OneBotV11Bot):
        await bot.set_group_ban(
            group_id=int(group_id),
            user_id=int(user_id),
            duration=int(duration),
        )
        return

    milky_cls = _milky_bot_cls()
    if milky_cls is not None and isinstance(bot, milky_cls):
        # TODO(milky): 与 nonebot-adapter-milky 源码核对动作名与参数命名。
        await bot.call_api(
            "mute_group_member",
            group_id=int(group_id),
            user_id=int(user_id),
            duration=int(duration),
        )
        return

    raise NotImplementedError(
        f"mute_group_member 暂不支持当前适配器："
        f"{type(bot).__module__}.{type(bot).__qualname__}"
    )


async def kick_group_member(
    bot: "Bot", *, group_id: int, user_id: int, reject_add_request: bool = False
) -> None:
    """将成员踢出群聊。

    ``reject_add_request`` 为 ``True`` 时同时拒绝该成员后续的加群申请。

    注意：踢人要求机器人为管理员或群主，否则 OneBot 端会抛出 ActionFailed。
    """
    if isinstance(bot, OneBotV11Bot):
        await bot.set_group_kick(
            group_id=int(group_id),
            user_id=int(user_id),
            reject_add_request=bool(reject_add_request),
        )
        return

    milky_cls = _milky_bot_cls()
    if milky_cls is not None and isinstance(bot, milky_cls):
        # TODO(milky): 与 nonebot-adapter-milky 源码核对动作名与参数命名。
        await bot.call_api(
            "kick_group_member",
            group_id=int(group_id),
            user_id=int(user_id),
            reject_add_request=bool(reject_add_request),
        )
        return

    raise NotImplementedError(
        f"kick_group_member 暂不支持当前适配器："
        f"{type(bot).__module__}.{type(bot).__qualname__}"
    )


async def send_group_message(bot: "Bot", *, group_id: int, message: Any) -> int | None:
    """向群聊发送一条消息，返回统一的消息 ID（可用于后续撤回/回应）。

    不依赖触发事件，适用于定时任务等场景（OneBot 的 ``message_id`` 与
    Milky 的 ``message_seq`` 在这里统一当作「消息 ID」使用）。
    后端未返回消息 ID 时返回 ``None``。
    """
    if isinstance(bot, OneBotV11Bot):
        result = await bot.send_group_msg(group_id=int(group_id), message=message)
        return _extract_message_id(result)

    milky_cls = _milky_bot_cls()
    if milky_cls is not None and isinstance(bot, milky_cls):
        # TODO(milky): 与 nonebot-adapter-milky 源码核对动作名与参数命名。
        result = await bot.call_api(
            "send_group_message",
            group_id=int(group_id),
            message=message,
        )
        return _extract_message_id(result)

    raise NotImplementedError(
        f"send_group_message 暂不支持当前适配器："
        f"{type(bot).__module__}.{type(bot).__qualname__}"
    )


async def recall_message(bot: "Bot", *, group_id: int, message_id: int) -> None:
    """撤回一条群消息。

    ``message_id`` 为本模块统一的「消息 ID」（Milky 侧内部当作 ``message_seq``）。

    注意：撤回他人消息要求机器人为管理员或群主，且受 QQ 的时间窗（约 2 分钟）限制；
    超出范围时协议端会报错（OneBot 端通常抛出 ActionFailed）。
    """
    if isinstance(bot, OneBotV11Bot):
        await bot.delete_msg(message_id=int(message_id))
        return

    milky_cls = _milky_bot_cls()
    if milky_cls is not None and isinstance(bot, milky_cls):
        # TODO(milky): 与 nonebot-adapter-milky 源码核对动作名与参数命名。
        await bot.call_api(
            "recall_group_message",
            group_id=int(group_id),
            message_seq=int(message_id),
        )
        return

    raise NotImplementedError(
        f"recall_message 暂不支持当前适配器："
        f"{type(bot).__module__}.{type(bot).__qualname__}"
    )


async def react_to_message(
    bot: "Bot", *, group_id: int, message_id: int, emoji: str | int
) -> None:
    """对一条消息贴「表情回应」（QQ 群表情回应功能，区别于发送一条表情消息）。

    - ``emoji`` 为 ``int`` 时视为 QQ 系统 face ID；
      为 ``str`` 时原样传递（可能是 face ID 字符串或 unicode emoji，由协议端解释）。

    注意：
    - 这是 NapCat / LLOneBot 对 OneBot 11 的**扩展动作**，非标准；
      OneBot 标准协议端可能不支持。
    - OneBot 用 ``message_id`` 标识消息；Milky 用 ``message_seq``（命名不同），
      本函数对 Milky 接收 ``message_id`` 参数但内部当 ``message_seq`` 使用。
    """
    if isinstance(bot, OneBotV11Bot):
        await bot.call_api(
            "set_msg_emoji_like",
            message_id=int(message_id),
            emoji_id=str(emoji),
        )
        return

    milky_cls = _milky_bot_cls()
    if milky_cls is not None and isinstance(bot, milky_cls):
        # Milky 用 message_seq 标识消息，且区分 face / emoji 两种回应类型
        reaction_type = "face" if isinstance(emoji, int) else "emoji"
        await bot.call_api(
            "send_group_message_reaction",
            group_id=int(group_id),
            message_seq=int(message_id),
            reaction=str(emoji),
            reaction_type=reaction_type,
            is_add=True,
        )
        return

    raise NotImplementedError(
        f"react_to_message 暂不支持当前适配器："
        f"{type(bot).__module__}.{type(bot).__qualname__}"
    )
