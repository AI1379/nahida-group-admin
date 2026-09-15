"""入群人机验证：新成员入群后回答一道简单算术题，未通过则自动踢出。

流程：
1. 监听「群成员增加」事件，在群内 @ 新成员并随机出一道加/减/乘法题；
2. 新成员在时限内直接在群里回复答案（答对即通过验证）；
3. 超时或答错次数用尽 → 自动踢出（可选择同时拒绝其再次加群）；
4. 验证通过后撤回题目、答错提示与对方的回复，群里不留验证痕迹；
5. 管理员可用 ``/验证 放行|踢出|重发 @某人`` 人工干预，防止误伤真人。

为什么是算术题：广告机器人多是无人值守的批量脚本，只会把话术原样刷进群里，
不会读题、更不会在限时内回复一个数字；而真人只需回一个数字，成本极低。
加减法还能避免粘贴关键词/复制长文绕过（答案随机且必须算对）。

状态保存在内存中（与项目其它功能一致），进程重启后未完成的验证会丢失。
"""

from __future__ import annotations

import asyncio
import random
import re
import unicodedata
from dataclasses import dataclass, field

from nonebot import get_driver, logger, on_command, on_message, on_notice
from nonebot.adapters import Event
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupDecreaseNoticeEvent,
    GroupIncreaseNoticeEvent,
    GroupMessageEvent,
    Message,
    MessageSegment,
)
from nonebot.adapters.onebot.v11.exception import ActionFailed
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule

from nahida_group_admin.compat import (
    kick_group_member,
    recall_message,
    send_group_message,
)
from nahida_group_admin.config import VerificationConfig, get_config

__plugin_meta__ = PluginMetadata(
    name="入群人机验证 / Join Verification",
    description="新成员入群后需限时回答一道算术题，未通过则自动踢出，用于拦截广告机器人。New members must solve a simple arithmetic challenge or get kicked.",
    usage="""自动流程 / Automatic:
  1. 有人入群 → Bot 在群内 @ 他并出一道加/减/乘法题
  2. 他在时限内直接在群里回复答案（如：8）
  3. 答对即通过；超时或答错次数用尽会被自动踢出
  4. 通过后自动撤回题目、答错提示与对方的回复，群里不留痕迹

管理命令 / Admin commands:
  /验证 放行 @某人   — 直接通过其验证（误伤时手动放行）
  /验证 踢出 @某人   — 立即将其踢出
  /验证 重发 @某人   — 重新出题（重置次数与倒计时）
  /verify pass|kick|retry @someone

配置 / Config（config.yaml 的 verification 节）:
  verification.enabled          — 是否启用
  verification.timeout_seconds  — 答题时限（秒）
  verification.max_attempts     — 最大答题次数
  verification.operators        — 出题运算符（+ - ×）
  verification.kick_on_fail     — 失败是否自动踢出
  verification.recall_on_pass  — 通过后是否撤回问答
  verification.recall_on_fail  — 失败时是否也撤回问答
  其余字段见 config.example.yaml""",
    config=VerificationConfig,
)

config = get_config().verification
driver = get_driver()

# 从回复中提取第一个整数（含负号），题面/答案均为整数
_INT_PATTERN = re.compile(r"-?\d+")


@dataclass
class Challenge:
    """一条待完成的入群验证记录。

    ``key`` 为 ``(group_id, user_id)``：同一个人在不同群里各自独立验证，
    也天然支持「同一群内多人同时验证」。
    """

    bot: Bot = field(repr=False)
    group_id: int
    user_id: int
    question: str
    answer: int
    attempts: int = 0
    task: "asyncio.Task[None] | None" = field(default=None, repr=False)
    # 本次验证产生的消息 ID（题目、答错提示、对方的每次回复），用于通过后统一撤回
    message_ids: list[int] = field(default_factory=list)

    @property
    def key(self) -> tuple[int, int]:
        return (self.group_id, self.user_id)

    @property
    def remaining_attempts(self) -> int:
        return max(0, config.max_attempts - self.attempts)


# 活跃的验证记录：{(group_id, user_id): Challenge}
_challenges: dict[tuple[int, int], Challenge] = {}


# ── 出题与判题（纯函数，便于单独测试）──


def _generate_question(cfg: VerificationConfig) -> tuple[str, int]:
    """随机生成一道算术题，返回 ``(题面, 正确答案)``。"""
    operator = random.choice(cfg.operators)
    left = random.randint(cfg.number_min, cfg.number_max)
    right = random.randint(cfg.number_min, cfg.number_max)

    if operator == "+":
        return f"{left} + {right}", left + right
    if operator == "-":
        # 保证被减数不小于减数，答案始终为非负整数，方便真人直接回数字
        if left < right:
            left, right = right, left
        return f"{left} - {right}", left - right
    return f"{left} × {right}", left * right


def _parse_answer(text: str) -> int | None:
    """从回复文本中提取答案（取第一个整数），无法识别时返回 ``None``。

    兼容全角数字（``８`` → ``8``）与带前后缀的写法（``=8``、``答案是 8``）。
    """
    normalized = unicodedata.normalize("NFKC", text)
    match = _INT_PATTERN.search(normalized)
    return int(match.group()) if match else None


def _is_admin(event: GroupMessageEvent) -> bool:
    """检查用户是否为管理员（群主/管理员/超级用户）。"""
    if str(event.user_id) in driver.config.superusers:
        return True
    return event.sender.role in ("admin", "owner")


# ── 发送与踢人 ──


async def _send(bot: Bot, group_id: int, message: str | Message) -> tuple[bool, int | None]:
    """发送群消息，返回 ``(是否成功, 消息 ID)``。

    失败只记录日志（验证流程不应因提示语发送失败而中断）；消息 ID 可能为
    ``None``（协议端未返回），此时只是无法撤回该消息。
    """
    try:
        message_id = await send_group_message(bot, group_id=group_id, message=message)
    except ActionFailed as e:
        logger.warning(f"验证消息发送失败（group={group_id}）：{e}")
        return False, None
    except NotImplementedError as e:
        logger.warning(f"当前后端无法发送群消息：{e}")
        return False, None
    return True, message_id


async def _recall(bot: Bot, group_id: int, message_id: int) -> None:
    """撤回一条消息；失败只记录日志（撤回失败不应影响验证结果）。"""
    try:
        await recall_message(bot, group_id=group_id, message_id=message_id)
    except ActionFailed as e:
        logger.warning(f"撤回验证消息失败（group={group_id}, msg={message_id}）：{e}")
    except NotImplementedError as e:
        logger.warning(f"当前后端不支持撤回消息：{e}")


def _track(challenge: Challenge, message_id: int | None) -> None:
    """记录本次验证产生的消息 ID，供通过后统一撤回。"""
    if message_id is not None and message_id not in challenge.message_ids:
        challenge.message_ids.append(message_id)


async def _recall_tracked(challenge: Challenge) -> None:
    """撤回本次验证产生的全部消息（题目、答错提示、对方的回复）。

    撤回他人消息要求机器人为管理员/群主，且受 QQ 时间窗（约 2 分钟）限制，
    超出范围时协议端会报错，此处只记录日志、不影响验证结果。
    """
    for message_id in list(challenge.message_ids):
        await _recall(challenge.bot, challenge.group_id, message_id)
    challenge.message_ids.clear()


async def _kick(bot: Bot, group_id: int, user_id: int, reason: str) -> None:
    """踢出未通过验证的成员，并在群内说明结果。"""
    try:
        await kick_group_member(
            bot,
            group_id=group_id,
            user_id=user_id,
            reject_add_request=config.reject_add_request,
        )
    except ActionFailed as e:
        logger.warning(f"验证踢人失败（group={group_id}, user={user_id}）：{e}")
        await _send(
            bot,
            group_id,
            Message(
                f"验证未通过（{reason}），但我没有足够权限踢出 "
                f"{MessageSegment.at(user_id)}，请管理员手动处理～"
            ),
        )
        return
    except NotImplementedError as e:
        logger.warning(f"当前后端不支持踢人：{e}")
        return

    logger.info(f"入群验证未通过，已踢出 {user_id}（group={group_id}，原因：{reason}）")
    await _send(
        bot,
        group_id,
        Message(
            f"{MessageSegment.at(user_id)} 未通过人机验证（{reason}），已移出本群。"
        ),
    )


async def _bot_can_kick(bot: Bot, group_id: int) -> bool:
    """机器人在群内是否有踢人权限（管理员/群主）。

    查询失败时返回 ``True``（宁可多做一次验证，也不漏验）——真正踢人失败时
    会有额外提示，不会静默失效。
    """
    try:
        info = await bot.get_group_member_info(
            group_id=group_id, user_id=int(bot.self_id)
        )
    except (ActionFailed, NotImplementedError, AttributeError) as e:
        logger.warning(f"获取机器人自身群角色失败（group={group_id}）：{e}，仍继续验证。")
        return True
    return info.get("role") in ("admin", "owner")


# ── 验证生命周期 ──


def _cancel(challenge: Challenge) -> None:
    """取消某条验证记录：移出注册表并终止其超时任务。"""
    _challenges.pop(challenge.key, None)
    if challenge.task is not None and not challenge.task.done():
        challenge.task.cancel()


def _question_message(challenge: Challenge) -> Message:
    """构造题目消息。"""
    return Message(
        f"{MessageSegment.at(challenge.user_id)} 请完成人机验证后再发言：\n"
        f"{challenge.question} = ?\n"
        f"请在 {config.timeout_seconds} 秒内直接回复答案"
        f"（共 {config.max_attempts} 次机会）。"
    )


async def _start(bot: Bot, group_id: int, user_id: int) -> None:
    """给指定成员出题并启动倒计时。"""
    # 重复入群或管理员重发时，先作废旧题目（含其超时任务）
    existing = _challenges.get((group_id, user_id))
    if existing is not None:
        _cancel(existing)

    question, answer = _generate_question(config)
    challenge = Challenge(
        bot=bot,
        group_id=group_id,
        user_id=user_id,
        question=question,
        answer=answer,
    )
    _challenges[challenge.key] = challenge

    sent, message_id = await _send(bot, group_id, _question_message(challenge))
    if not sent:
        _cancel(challenge)  # 题目都没发出去，验证无从谈起
        return
    _track(challenge, message_id)

    challenge.task = asyncio.create_task(_expire(challenge))
    logger.info(f"入群验证开始：group={group_id} user={user_id} 题目={question}")


async def _expire(challenge: Challenge) -> None:
    """超时未作答则判定失败（成功/人工处理时该任务会被取消）。"""
    await asyncio.sleep(config.timeout_seconds)
    if _challenges.get(challenge.key) is not challenge:
        return  # 记录已被替换或清理，超时任务作废
    await _fail(challenge, f"超时 {config.timeout_seconds} 秒未作答")


async def _fail(challenge: Challenge, reason: str) -> None:
    """判定验证失败：按配置撤回问答、踢出，否则仅在群内提示。"""
    _cancel(challenge)
    if config.recall_on_fail:
        await _recall_tracked(challenge)
    if config.kick_on_fail:
        await _kick(challenge.bot, challenge.group_id, challenge.user_id, reason)
    else:
        await _send(
            challenge.bot,
            challenge.group_id,
            Message(
                f"{MessageSegment.at(challenge.user_id)} 未通过人机验证（{reason}），"
                f"请管理员手动处理～"
            ),
        )


# ── 事件响应器 ──


join_notice = on_notice(block=False)


@join_notice.handle()
async def handle_group_increase(bot: Bot, event: GroupIncreaseNoticeEvent) -> None:
    """新成员入群：出题验证。"""
    if not config.enabled:
        return

    if str(event.user_id) == str(bot.self_id):
        return  # 机器人自己加入群聊，无需验证

    if event.sub_type == "invite" and not config.verify_invite:
        logger.debug(f"群 {event.group_id} 的 {event.user_id} 系受邀入群，按配置跳过验证。")
        return

    if config.require_bot_admin and not await _bot_can_kick(bot, event.group_id):
        logger.warning(
            f"机器人不是群 {event.group_id} 的管理员，无法执行踢人，跳过入群验证。"
            f"（可设置 verification.require_bot_admin: false 强制验证）"
        )
        return

    await _start(bot, event.group_id, event.user_id)


leave_notice = on_notice(block=False)


@leave_notice.handle()
async def handle_group_decrease(event: GroupDecreaseNoticeEvent) -> None:
    """成员退群/被踢：清理其未完成的验证，避免超时后重复操作。"""
    challenge = _challenges.get((event.group_id, event.user_id))
    if challenge is not None:
        _cancel(challenge)
        logger.debug(f"成员 {event.user_id} 已离开群 {event.group_id}，清理其入群验证。")


def _has_pending_challenge(event: Event) -> bool:
    """规则：该事件是否来自「正待验证」的群成员。"""
    group_id = getattr(event, "group_id", None)
    user_id = getattr(event, "user_id", None)
    if group_id is None or user_id is None:
        return False
    return (int(group_id), int(user_id)) in _challenges


# priority=1 + block=True：验证期间的回复只用于答题，不再触发其它插件的匹配
answer_msg = on_message(rule=Rule(_has_pending_challenge), priority=1, block=True)


@answer_msg.handle()
async def handle_answer(bot: Bot, event: GroupMessageEvent) -> None:
    """处理待验证成员的群消息：答对通过，答错计数。"""
    challenge = _challenges.get((event.group_id, event.user_id))
    if challenge is None:  # 理论上规则已过滤，此处仅作防御
        return

    text = event.get_plaintext().strip()
    if not text:
        return  # 纯图片/表情等非文本消息不计入答题次数

    _track(challenge, event.message_id)  # 记录对方的回复，通过后一并撤回

    parsed = _parse_answer(text)
    if parsed == challenge.answer:
        _cancel(challenge)
        logger.info(f"入群验证通过：group={event.group_id} user={event.user_id}")
        if config.recall_on_pass:
            await _recall_tracked(challenge)
        if config.welcome_message:
            await _send(
                bot,
                event.group_id,
                Message(
                    f"{MessageSegment.at(challenge.user_id)} {config.welcome_message}"
                ),
            )
        return

    challenge.attempts += 1
    remaining = challenge.remaining_attempts
    logger.debug(
        f"入群验证答错：group={event.group_id} user={event.user_id} "
        f"回复={text!r} 期望={challenge.answer} 剩余次数={remaining}"
    )

    if remaining <= 0:
        await _fail(challenge, f"连续 {config.max_attempts} 次回答错误")
        return

    _, hint_message_id = await _send(
        bot,
        event.group_id,
        f"答案不对哦，再想想～题目：{challenge.question} = ?（还剩 {remaining} 次机会）",
    )
    _track(challenge, hint_message_id)


# ── 管理员人工干预 ──

_PASS_KEYWORDS = {"放行", "通过", "pass", "approve", "ok", "yes"}
_KICK_KEYWORDS = {"踢出", "踢", "kick", "reject", "拒绝"}
_RESET_KEYWORDS = {"重发", "重置", "重出", "reset", "retry", "again"}

verify_cmd = on_command("验证", aliases={"verify", "人机验证"}, block=True)


@verify_cmd.handle()
async def handle_verify(
    bot: Bot,
    event: GroupMessageEvent,
    args: Message = CommandArg(),
) -> None:
    """管理员人工干预：放行 / 踢出 / 重发题目。"""
    if not _is_admin(event):
        await verify_cmd.finish("仅管理员可用该命令～")

    at_segments = [seg for seg in args if seg.type == "at"]
    action = args.extract_plain_text().strip().lower()

    if not at_segments or not action:
        await verify_cmd.finish(
            "用法：\n"
            "  /验证 放行 @某人 — 直接通过其验证\n"
            "  /验证 踢出 @某人 — 立即踢出\n"
            "  /验证 重发 @某人 — 重新出题"
        )

    target_user_id = int(at_segments[0].data["qq"])
    challenge = _challenges.get((event.group_id, target_user_id))

    if action in _PASS_KEYWORDS:
        if challenge is None:
            await verify_cmd.finish("该成员当前没有待完成的入群验证～")
        _cancel(challenge)
        logger.info(
            f"管理员放行入群验证：group={event.group_id} user={target_user_id} "
            f"by={event.user_id}"
        )
        if config.recall_on_pass:
            await _recall_tracked(challenge)
        await verify_cmd.finish(
            Message(f"已放行 {MessageSegment.at(target_user_id)}，验证通过～")
        )

    if action in _KICK_KEYWORDS:
        if challenge is None:
            await verify_cmd.finish("该成员当前没有待完成的入群验证～")
        _cancel(challenge)
        logger.info(
            f"管理员判定验证不通过：group={event.group_id} user={target_user_id} "
            f"by={event.user_id}"
        )
        if config.recall_on_fail:
            await _recall_tracked(challenge)
        await _kick(bot, event.group_id, target_user_id, "管理员判定未通过")
        return

    if action in _RESET_KEYWORDS:
        await _start(bot, event.group_id, target_user_id)
        await verify_cmd.finish(
            Message(f"已为 {MessageSegment.at(target_user_id)} 重新出题～")
        )

    await verify_cmd.finish("无法识别该操作，支持：放行 / 踢出 / 重发")


@driver.on_shutdown
async def _cleanup_challenges() -> None:
    """进程退出前取消所有倒计时任务，避免遗留 pending task。"""
    for challenge in list(_challenges.values()):
        _cancel(challenge)
