# Nahida Group Admin 🥛🐧

> 一个面向 QQ 群的自动化管理机器人，让群管理像「智慧之神」一样省心。

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-%3E%3D3.14-blue.svg)](.python-version)
[![Built with NoneBot2](https://img.shields.io/badge/Built%20with-NoneBot2-ea5252.svg)](https://nonebot.dev/)
[![Backend: OneBot 11 | Milky](https://img.shields.io/badge/Backend-OneBot%2011%20%7C%20Milky-green.svg)](#-支持的后端)

**Nahida Group Admin** 把日常群管理中重复、繁琐的工作交给机器人：成员自助领取头衔、入群审批走群内投票、陶片放逐、自助禁言、戳一戳与命令文本互动等。它底层基于 [NoneBot2](https://nonebot.dev/) 构建，同时兼容 [OneBot 11](https://github.com/botuniverse/onebot-11) 与 [Milky](https://milky.ntqqrev.org/) 两套后端协议——通过一层适配器门面屏蔽二者差异，让你自由选择协议端实现而不必改动业务逻辑。

> [!NOTE]
> 🚧 **项目状态：开发中。** 已基于 NoneBot2 搭好骨架，并完成 5 个功能（OneBot 11 后端已验证）：**自助派发头衔、自助禁言、戳一戳互动、关键词互动、陶片放逐**。仅剩入群审批待开发，下文标注 🚧 的部分为目标设计，配置项与命令格式可能调整。欢迎通过 Issue / PR 参与。

---

## ✨ 功能特性

- **🎖️ 自助派发头衔** ✅
  群成员通过命令自助设置自己的群头衔（群专属头衔），无需管理员逐个手动操作。管理员还可用 `@某人` 设置他人头衔。可配置头衔长度、敏感词与冷却时间等限制。

- **🔇 自助禁言** ✅
  允许群成员在规则约束下对特定成员发起禁言。典型场景：某个挂着特定头衔（例如头衔为 `bot` 的机器人小号）的成员，允许普通群员对其自助禁言。可基于「头衔 / 角色」配置「谁可以禁言谁、禁言多久」。

- **👉 戳一戳互动** ✅
  响应戳一戳（双击头像 / Poke）事件，被戳时自动戳回去，增添群聊趣味性。

- **💬 关键词互动** ✅
  监听消息，匹配预设关键词时回复随机表情。支持 **Unicode emoji** 与 **QQ face ID** 混合格式，关键词与表情列表均可配置。

- **🏺 陶片放逐（Ostracism）** ✅
  借鉴古雅典「陶片放逐制」的群内投票踢人机制：管理员发起后，成员通过回复通知并贴特定表情投票，达到阈值即自动踢出。票数阈值支持「固定票数」与「群成员百分比」双模式，取最小值（`-1` 表示不考虑该项）。

- **📨 入群审批通知** 🚧
  当有人申请加群时，机器人在群内推送一条包含申请人信息与验证消息的通知。**任意管理员**只需「回复」这条通知消息即可决定通过或拒绝，审批结果会同步反馈到群内。

- **🔌 双后端兼容**
  同一套业务逻辑可运行在 **OneBot 11** 或 **Milky** 之上，通过统一的适配器门面抽象消息收发、事件分发与群管理操作。

---

## 🔗 支持的后端

本项目借助 NoneBot2 的适配器机制兼容两套主流 QQ 机器人接口标准，二选一即可运行：

| 后端 | 说明 | NoneBot 适配器 | 常见协议端实现 |
| --- | --- | --- | --- |
| [**OneBot 11**](https://github.com/botuniverse/onebot-11) | 生态最成熟、实现最广泛的 QQ 机器人通信协议。 | [`nonebot-adapter-onebot`](https://github.com/nonebot/adapter-onebot) | [NapCat](https://github.com/NapNeko/NapCatQQ)、[Lagrange.Core](https://github.com/LagrangeDev/Lagrange.Core) 等 |
| [**Milky**](https://milky.ntqqrev.org/) | 基于 HTTP / WebSocket 的新一代 QQ 机器人应用接口标准，强类型、易上手。 | `nonebot-adapter-milky` | [tanebi](https://github.com/SaltifyDev/tanebi) 等 |

> **目前以 OneBot 11 为主要、已验证的后端**；Milky 为可选项（见 [安装](#安装) 中的 `--extra milky`），仍在完善中。
>
> Milky 的许多设计直接或间接源自 OneBot 11，但二者并非扩展关系，连接方式与动作 API 各不相同。本项目在 [`nahida_group_admin/compat`](nahida_group_admin/compat) 这层门面里按后端类型分发，对上层功能保持一致行为。

---

## 🚀 快速开始

### 环境要求

- Python **>= 3.14**
- [uv](https://github.com/astral-sh/uv)（依赖与虚拟环境管理工具）
- 一个可用的 **OneBot 11** 协议端（如 [NapCat](https://github.com/NapNeko/NapCatQQ) / [Lagrange.Core](https://github.com/LagrangeDev/Lagrange.Core)）；Milky 协议端为可选

### 安装

```bash
git clone https://github.com/AI1379/nahida-group-admin.git
cd nahida-group-admin

# 安装依赖（默认仅 OneBot 11 后端）
uv sync

# 可选：额外启用 Milky 后端
uv sync --extra milky
```

### 配置

```bash
# 从模板创建本地配置（.env 已被 .gitignore 忽略，不会提交）
cp .env.example .env
# 按需修改 .env，详见下方「配置」一节
```

### 运行

```bash
uv run python bot.py
```

### 连接协议端

以 OneBot 11 **反向 WebSocket** 为例，在 NapCat / Lagrange 等协议端里把上报（反向 WS）地址设为：

```
ws://127.0.0.1:8080/onebot/v11/ws
```

若协议端设置了 access token，请把相同的值填进 `.env` 的 `ONEBOT_ACCESS_TOKEN`。连接成功后，在群里发送 `/头衔 测试` 即可体验。

---

## ⚙️ 配置

配置遵循 NoneBot2 约定，写在项目根目录的 `.env` 文件中（完整带注释的模板见 [`.env.example`](.env.example)）。常用字段：

```dotenv
# 后端连接 Driver：~fastapi 提供反向 WS 服务端，~httpx/~websockets 提供客户端能力
DRIVER=~fastapi+~httpx+~websockets
HOST=127.0.0.1
PORT=8080

# 命令前缀，例如 /头衔
COMMAND_START=["/"]
# 超级用户（后续入群审批等授权功能会用到），填 QQ 号字符串
SUPERUSERS=[]

# OneBot 11 协议端的 access token（如已设置）
ONEBOT_ACCESS_TOKEN=

# —— 自助头衔插件 ——
# 头衔最大字符数
TITLE_MAX_LENGTH=6
# 修改冷却（秒），0 表示不限制
TITLE_COOLDOWN=3600
# 禁止出现在头衔中的子串，如 ["管理","群主"]
TITLE_BLACKLIST=[]
```

> 正向 WS（机器人主动连接协议端）等其它连接方式的字段，见 `.env.example` 中的说明。

---

## 💬 命令一览

> 命令前缀默认为 `/`（由 `.env` 的 `COMMAND_START` 配置）。

| 命令 | 功能 | 谁可以用 | 状态 |
| --- | --- | --- | --- |
| `/头衔 <内容>` | 设置自己的群专属头衔（`/头衔 清除` 可移除） | 所有成员 | ✅ 已实现 |
| `/头衔 @某人 <内容>` | 管理员设置某人的头衔 | 管理员 | ✅ 已实现 |
| `/禁言 @某人 <时长>` | 在规则允许范围内自助禁言（支持 `5m`/`30s`/`1h`） | 视配置而定 | ✅ 已实现 |
| `/放逐 @某人` 或 `/放逐 <QQ号>` | 发起陶片放逐投票 | 管理员 | ✅ 已实现 |
| 戳一戳机器人 | 机器人戳回去 | 所有成员 | ✅ 已实现 |
| 包含关键词的消息 | 回复随机表情 | 所有成员 | ✅ 已实现 |
| 回复入群通知 `同意` / `拒绝` | 通过 / 拒绝入群申请 | 管理员 | 🚧 计划中 |

> [!IMPORTANT]
> 设置群专属头衔是 QQ 的**群主专属**操作——机器人账号需为该群**群主**，否则操作会失败（仅管理员无效）。

---

## 🗺️ 路线图

- [x] 适配器门面：统一抽象后端的事件与动作（OneBot 11 就绪；Milky 进行中）
- [x] 配置加载（NoneBot2 + `.env`）
- [x] 自助派发头衔
- [x] 自助禁言（基于头衔 / 角色的规则）
- [x] 戳一戳互动
- [x] 关键词互动（支持 Unicode emoji / QQ face ID）
- [x] 陶片放逐投票（固定票数 / 百分比双模式）
- [ ] 入群审批（群内通知 + 管理员回复审批）
- [ ] 完善 Milky 后端适配
- [ ] 完善文档与部署示例

---

## 🛠️ 开发

```bash
uv sync
uv run python bot.py
```

### 项目结构

```
bot.py                           # 启动入口：init → 注册适配器 → 加载插件 → run
nahida_group_admin/
├── compat/
│   └── group.py                 # 跨适配器的群管理能力门面（按 Bot 类型分发）
└── plugins/
    ├── title/                   # 🎖️ 自助派发头衔
    ├── mute/                    # 🔇 自助禁言
    ├── interaction/             # 👉 戳一戳 + 关键词互动
    └── ostracism/               # 🏺 陶片放逐
.env.example                     # 配置模板
```

### 新增一个功能

1. 在 `nahida_group_admin/plugins/` 下新建一个 NoneBot 插件；
2. 所有群管理动作统一调用 `nahida_group_admin.compat` 里的门面函数（它会按当前 Bot 类型分发到 OneBot / Milky），新动作就在门面里补一个函数；
3. 在 `bot.py` 中 `nonebot.load_plugin(...)` 注册该插件。

欢迎贡献！如果你有功能建议或发现了问题，请提交 [Issue](https://github.com/AI1379/nahida-group-admin/issues) 或 Pull Request。提交前请确保说明清楚改动的动机与影响。

---

## 📄 许可证

本项目基于 [**GNU AGPL-3.0**](LICENSE) 许可证开源。这意味着如果你修改本项目并通过网络向用户提供服务，需要按照该许可证的要求公开相应的源代码。

---

## 🙏 致谢

- [NoneBot2](https://nonebot.dev/) — 跨平台 Python 异步机器人框架
- [OneBot 11](https://github.com/botuniverse/onebot-11) — 广泛使用的 QQ 机器人通信协议
- [Milky](https://milky.ntqqrev.org/) — 新一代 QQ 机器人应用接口标准
- [NapCat](https://github.com/NapNeko/NapCatQQ)、[Lagrange.Core](https://github.com/LagrangeDev/Lagrange.Core) — 优秀的协议端实现
- [QQ 机器人官方表情对象文档](https://bot.q.qq.com/wiki/develop/api-v2/openapi/emoji/model.html) — QQ 表情 ID 完整列表

> 项目名取自《原神》中的草神 **纳西妲（Nahida）**——智慧与知识之神，愿她也能照看好你的群聊。 🌿
