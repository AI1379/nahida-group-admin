"""自助派发头衔：群成员通过命令自助设置自己的群专属头衔。

注意：QQ 仅允许「群主」设置成员专属头衔，机器人账号需为群主，否则操作会失败。
"""

import time

from nonebot import get_driver, get_plugin_config, logger, on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment
from nonebot.adapters.onebot.v11.exception import ActionFailed
# At 段在 OneBot V11 中是 MessageSegment 类型为 'at'，CQ 码格式：[CQ:at,qq=xxx]
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from nahida_group_admin.compat import set_special_title

from .config import TitleConfig

__plugin_meta__ = PluginMetadata(
    name="自助头衔 / Self-Service Title",
    description="群成员自助设置 / 清除自己的群专属头衔。支持中英文命令与参数。Members can set/clear their own group special title. Supports bilingual commands and parameters.",
    usage="""命令 / Commands:
  /头衔 <内容>           — 设置自己的头衔
  /头衔 @某人 <内容>     — 管理员设置某人的头衔
  /头衔 清除             — 移除自己的头衔
  /title <text>          — set own title
  /title @someone <text> — admin sets someone's title
  /title clear           — clear title

清除参数 / Clear params: 清除、删除、clear、remove、none

限制 / Limits:
  - 头衔长度、敏感词由配置决定
  - 冷却时间对「设置自己」生效
  - 「设置他人」仅限管理员，无冷却限制""",
    config=TitleConfig,
)

config = get_plugin_config(TitleConfig)
driver = get_driver()

# 简单的内存级冷却记录：{(group_id, user_id): 上次设置的时间戳}
# 注意：进程重启后清空；如需持久化可后续接入存储。
# ⚠️ 冷却是「按群成员」的：每个人的冷却独立计算，不是全群共享。
_last_set: dict[tuple[int, int], float] = {}


def _is_admin(bot: Bot, event: GroupMessageEvent) -> bool:
    """检查用户是否为管理员（群主/管理员/超级用户）。"""
    # 超级用户（.env 配置的 SUPERUSERS）
    superusers = driver.config.superusers
    if str(event.user_id) in superusers:
        return True

    # 群内角色：owner(群主) / admin(管理员) / member(普通成员)
    sender_role = event.sender.role
    return sender_role in ("admin", "owner")

_CLEAR_KEYWORDS = {"清除", "删除", "清空", "clear", "remove", "none", "reset", "unset"}

title_cmd = on_command(
    "头衔",
    aliases={"title", "改头衔", "设置头衔", "set_title", "mytitle", "settitle"},
    block=True,
)


@title_cmd.handle()
async def handle_title(
    bot: Bot,
    event: GroupMessageEvent,
    args: Message = CommandArg(),
) -> None:
    group_id, user_id = event.group_id, event.user_id

    # 解析消息中的 @ 提及（OneBot V11 的 at 段类型为 'at'）
    at_segments = [seg for seg in args if seg.type == "at"]
    has_at = len(at_segments) > 0

    # 提取纯文本（排除 @ 段）
    raw = args.extract_plain_text().strip()

    if not raw and not has_at:
        await title_cmd.finish(
            "用法 / Usage:\n"
            "  /头衔 <内容>           — 设置自己的头衔\n"
            "  /头衔 @某人 <内容>     — 管理员设置某人的头衔\n"
            "  /title clear           — clear title\n"
            "清除参数: 清除、删除、clear、remove、none"
        )

    # 模式判断：有 @ 则为「设置他人」，仅管理员可用
    target_user_id = None
    is_setting_others = False

    if has_at:
        if not _is_admin(bot, event):
            await title_cmd.finish("设置他人的头衔仅限管理员使用～")
        target_user_id = int(at_segments[0].data["qq"])
        is_setting_others = True
    else:
        target_user_id = user_id

    # 解析头衔内容：优先用参数文本，否则为清除
    clearing = raw in _CLEAR_KEYWORDS
    new_title = "" if clearing else raw

    # 仅在设置非空头衔时做内容校验
    if new_title:
        if len(new_title) > config.title_max_length:
            await title_cmd.finish(
                f"头衔太长啦，最多 {config.title_max_length} 个字符～"
            )
        if any(w and w in new_title for w in config.title_blacklist):
            await title_cmd.finish("这个头衔包含不被允许的内容，换一个吧～")

    # 冷却检查：仅对「设置自己」生效；管理员操作他人无冷却
    if not is_setting_others:
        now = time.time()
        last = _last_set.get((group_id, user_id))
        if last is not None and config.title_cooldown > 0:
            remaining = int(config.title_cooldown - (now - last))
            if remaining > 0:
                await title_cmd.finish(f"操作太频繁啦，请 {remaining} 秒后再试～")

    try:
        await set_special_title(
            bot, group_id=group_id, user_id=target_user_id, title=new_title
        )
    except ActionFailed as e:
        logger.warning(f"设置头衔失败（group={group_id}, user={target_user_id}）：{e}")
        await title_cmd.finish("设置失败：我可能不是本群群主，无法设置头衔 😢")
    except NotImplementedError:
        await title_cmd.finish("当前后端暂不支持设置头衔～")

    # 记录冷却（仅设置自己时）
    if not is_setting_others:
        _last_set[(group_id, user_id)] = time.time()

    # 回执文本
    if is_setting_others:
        await title_cmd.finish(
            Message(f"已清除 {MessageSegment.at(target_user_id)} 的头衔～")
            if clearing
            else Message(f"已将 {MessageSegment.at(target_user_id)} 的头衔设置为「{new_title}」🎉")
        )
    else:
        await title_cmd.finish(
            "已清除你的头衔～" if clearing else f"已将你的头衔设置为「{new_title}」🎉"
        )
