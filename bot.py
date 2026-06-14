"""Nahida Group Admin —— NoneBot2 启动入口。

以 OneBot V11 为主适配器；若安装了 Milky 适配器（uv sync --extra milky）则一并注册，
作为次要后端。运行： ``uv run python bot.py``
"""

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter


def main() -> None:
    nonebot.init()

    driver = nonebot.get_driver()
    driver.register_adapter(OneBotV11Adapter)

    # Milky 为可选 / 次要后端：仅在安装了对应适配器时注册。
    try:
        from nonebot.adapters.milky import Adapter as MilkyAdapter
    except ImportError:
        nonebot.logger.info("未安装 Milky 适配器，仅以 OneBot V11 运行。")
    else:
        driver.register_adapter(MilkyAdapter)

    # 加载功能插件
    nonebot.load_plugin("nahida_group_admin.plugins.title")
    nonebot.load_plugin("nahida_group_admin.plugins.mute")

    nonebot.run()


if __name__ == "__main__":
    main()
