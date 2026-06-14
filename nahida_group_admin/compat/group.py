"""跨适配器的群管理能力门面。

NoneBot 统一了事件分发与运行生命周期，但不同适配器暴露的「动作 API」在名称与参数上
并不一致。本模块把上层功能所需的群管理操作，收敛成一组与适配器无关的函数，内部再按
Bot 的具体类型分发到对应适配器的调用。

当前以 OneBot V11 为主实现；Milky 为次要路径，部分动作名 / 参数仍需与
``nonebot-adapter-milky`` 源码核对（见各处 TODO）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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
