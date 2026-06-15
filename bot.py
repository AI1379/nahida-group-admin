"""Nahida Group Admin —— NoneBot2 启动入口。

配置统一从 ``config.yaml`` 加载（见 ``nahida_group_admin.config``），框架设置通过
``nonebot.init(**...)`` 注入，插件配置通过模块单例 ``get_config()`` 访问。

运行： ``uv run python bot.py``
"""

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

from nahida_group_admin.config import load_config


def main() -> None:
    # 1. 加载并校验 YAML 配置（单一配置源）
    cfg = load_config()

    # 2. 框架设置注入 NoneBot
    nonebot.init(
        driver=cfg.driver,
        host=cfg.host,
        port=cfg.port,
        log_level=cfg.log_level,
        command_start=cfg.command_start,
        superusers=cfg.superusers,
        onebot_access_token=cfg.onebot_access_token,
    )

    driver = nonebot.get_driver()
    driver.register_adapter(OneBotV11Adapter)

    # Milky 为可选 / 次要后端：仅在安装了对应适配器时注册。
    try:
        from nonebot.adapters.milky import Adapter as MilkyAdapter
    except ImportError:
        nonebot.logger.info("未安装 Milky 适配器，仅以 OneBot V11 运行。")
    else:
        driver.register_adapter(MilkyAdapter)

    # 注册全局群聊白名单钩子（导入即生效，对所有 matcher 与后端适配器生效）
    import nahida_group_admin.common.whitelist  # noqa: F401

    # 加载功能插件
    nonebot.load_plugin("nahida_group_admin.plugins.title")
    nonebot.load_plugin("nahida_group_admin.plugins.mute")
    nonebot.load_plugin("nahida_group_admin.plugins.interaction")
    nonebot.load_plugin("nahida_group_admin.plugins.ostracism")

    nonebot.run()


if __name__ == "__main__":
    main()
