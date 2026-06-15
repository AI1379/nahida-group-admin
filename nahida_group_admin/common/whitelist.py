"""群聊白名单：全局事件过滤器。

通过 NoneBot2 的 ``event_preprocessor`` 在所有事件分发给任何 matcher 之前拦截：
仅当事件所属群在白名单中时才放行。白名单为空时表示不限制（放行所有群）。

该模块只需被导入（``import nahida_group_admin.common.whitelist``）即注册全局钩子，
对所有 matcher 类型（on_command / on_message / on_notice）与所有后端适配器生效。

配置从集中式 ``config.yaml`` 的 ``group_whitelist`` 读取（见
``nahida_group_admin.config``）。
"""

from nonebot.exception import IgnoredException
from nonebot.message import event_preprocessor

from nahida_group_admin.config import get_config

config = get_config()


@event_preprocessor
async def group_whitelist_filter(event) -> None:  # noqa: ANN001 - NoneBot 依赖注入，类型为 Event
    """过滤非白名单群的所有事件。

    - 非群事件（无 ``group_id``，如私聊）：放行
    - 白名单为空：放行所有群（功能未启用）
    - 群在白名单中：放行
    - 否则：抛出 ``IgnoredException``，该事件被忽略
    """
    group_id = getattr(event, "group_id", None)
    if group_id is None:
        return  # 非群事件，放行
    if config.group_whitelist and group_id not in config.group_whitelist:
        raise IgnoredException(f"群 {group_id} 不在白名单中")
