# AstrBot Synology Chat 适配器插件

> 仓库/分发文件夹名称可使用：`Synology-chat-adapter`

这是一个基于 **AstrBot 平台适配器插件机制** 编写的 Synology Chat 对接示例，实现思路是：

- **接收消息**：使用 Synology Chat 的 **传出 Webhook / 斜线指令** 把消息投递到 AstrBot
- **发送消息**：使用 Synology Chat 的 **机器人外部 API（`SYNO.Chat.External`）** 回发消息
- **运行方式**：优先使用 AstrBot **统一 Webhook 模式**
- **平台图标**：通过 AstrBot 平台适配器的 `logo_path` 机制，把图标随插件一起分发

## 文件说明

- `metadata.yaml`：AstrBot 插件元数据，**必须存在**
- `main.py`：AstrBot 插件入口，负责导入并注册适配器
- `synology_chat_adapter.py`：平台适配器实现
- `synology_chat_event.py`：消息事件实现，负责把 AstrBot 输出回发到 Synology Chat

## 推荐目录结构

如果你在本地开发、打包压缩包、或者放到 Git 仓库中，外层目录可以命名为：

```text
Synology-chat-adapter/
```

但请注意：**AstrBot 真正安装到 `data/plugins/` 下时，插件目录名仍应使用 `synochat_adapter`**，因为 AstrBot 会读取 `metadata.yaml` 里的 `name`，并要求它是合法 Python 模块名，不能包含 `-`。

将本目录整体放入 AstrBot 插件目录，例如：

```text
data/plugins/synochat_adapter/
├── assets/
│   └── synology-chat.svg
├── metadata.yaml
├── main.py
├── synology_chat_adapter.py
├── synology_chat_event.py
└── README.md
```

## 平台图标说明

本插件已在适配器注册时声明：

```python
logo_path="assets/synology-chat.svg"
```

在支持 `logo_path` 透传的 AstrBot 版本中，WebUI 新增平台时会自动读取并显示该图标，因此更适合直接打包分发到多台 AstrBot，而无需为每台实例单独修改前端图标映射。

## 重要：修复你当前遇到的安装报错

你现在报错：

```text
未找到 metadata.yaml，无法获取插件目录名。
```

这是因为 **AstrBot 新版插件系统强依赖插件目录下的 `metadata.yaml`**。仅有 `main.py` 不够，插件安装器和插件管理器会先读取 `metadata.yaml`，再根据其中的 `name` 作为模块名加载插件。

因此本插件现在已经补齐：

- `metadata.yaml`
- 符合 AstrBot 常规插件结构的 `main.py`

另外说明一下：如果你在独立工作区里直接打开这些文件，编辑器可能会提示：

```text
无法解析匯入 "astrbot.api"
```

这通常只是因为 **当前 VS Code 打开的目录不是 AstrBot 本体项目/虚拟环境**，导致 Pylance 无法解析 AstrBot 运行时依赖；**不代表插件结构错误**。只要把本插件目录放进实际的 `AstrBot/data/plugins/synology_chat_adapter/` 下，由 AstrBot 本体加载即可。

其中 `metadata.yaml` 里的 `name` 必须是合法 Python 模块名，并且应与插件目录名保持一致，推荐直接使用：

```yaml
name: synochat_adapter
```

所以你的插件安装目录也请使用：

```text
data/plugins/synochat_adapter
```

也就是说，推荐这样理解：

- **仓库名 / 压缩包外层目录名**：`Synology-chat-adapter`
- **AstrBot 实际插件目录名**：`synochat_adapter`
- **metadata.yaml 中的 `name`**：`synochat_adapter`

## Synology Chat 侧配置

### 1. 建立机器人 / 整合

在 Synology Chat 中创建机器人整合，并记录：

- Chat 基础地址，例如：`https://chat.example.com`
- Bot Token
- 或直接复制 Synology Chat 提供的完整传入链接（推荐）

例如 Synology Chat 往往会给出类似这样的链接：

```text
https://nas-ip:port/webapi/entry.cgi?api=SYNO.Chat.External&method=chatbot&version=2&token=%22*********%22
```

本插件现在支持直接读取这条完整链接，并自动提取：

- `base_url`
- `token`

同时会自动去掉 URL 里可能出现的 `%22...%22` 外层引号，避免因为重复填写或循环引用 token 导致配置混乱。

### 2. 配置传出 Webhook

在 Synology Chat 的整合功能中配置 **传出 Webhook** 或 **斜线指令**：

- URL：填写 AstrBot 统一 Webhook 地址
- 触发词：按你的需要设置

如果你的 AstrBot 公开地址是：

```text
https://bot.example.com/api/platform/webhook/xxxxxxxx
```

则把这个地址填入 Synology Chat 的 Webhook URL。

## AstrBot 侧配置

适配器注册后，可在平台配置里增加类似配置：

```json
{
  "id": "synology_chat",
  "type": "synochat_adapter",
  "enable": true,
  "base_url": "",
  "incoming_webhook_url": "https://nas-ip:port/webapi/entry.cgi?api=SYNO.Chat.External&method=chatbot&version=2&token=%22YOUR_BOT_TOKEN%22",
  "bot_token": "",
  "outgoing_token": "",
  "request_timeout": 15,
  "verify_token": true,
  "unified_webhook_mode": true,
  "webhook_uuid": ""
}
```

说明：

- `incoming_webhook_url`：可直接填写 Synology Chat 提供的完整 chatbot 链接；插件会自动提取 `base_url` 和 `bot_token`
- `base_url`：Synology Chat 的访问根地址；如果已填写 `incoming_webhook_url`，可留空
- `bot_token`：用于调用 `SYNO.Chat.External` 发送消息；如果已填写 `incoming_webhook_url`，可留空
- `outgoing_token`：如你的传出 Webhook 使用单独 token，可填这里；为空时默认用 `bot_token` 校验
- `verify_token`：是否校验 Synology Chat 发来的 token
- `unified_webhook_mode`：建议设为 `true`；启用后 AstrBot 会自动分配 `webhook_uuid`
- `webhook_uuid`：通常无需手动填写，AstrBot 会像其他统一 Webhook 平台一样自动生成

### 推荐配置方式

推荐你只填写：

```json
{
  "type": "synochat_adapter",
  "incoming_webhook_url": "https://nas-ip:port/webapi/entry.cgi?api=SYNO.Chat.External&method=chatbot&version=2&token=%22YOUR_BOT_TOKEN%22",
  "outgoing_token": "",
  "verify_token": true
}
```

这样可以避免手动复制两次 token，减少填错、套娃引用或后续更换 token 时遗漏更新的问题。

### 关于统一 Webhook UUID

统一 Webhook 模式下，`webhook_uuid` 不是你手动规划的固定值，而是由 AstrBot 在平台配置初始化时自动生成。插件侧只需要实现 `webhook_callback()` 并在运行时复用这个 UUID 即可。

因此 Synology Chat 这边的正确接法是：

1. 在 AstrBot 中启用 `unified_webhook_mode`
2. 由 AstrBot 自动生成 `webhook_uuid`
3. 将最终的 `/api/platform/webhook/{uuid}` 地址填回 Synology Chat 的传出 Webhook / 斜线指令

插件启动后也会像参考适配器一样输出统一 Webhook 地址日志，方便直接复制使用。

## 当前实现能力

### 已支持

- 接收 Synology Chat 传出 Webhook 消息
- 接收斜线指令投递的数据（按普通文本消息处理）
- 文本消息回发
- 图片消息自动降级为“文本 + 图片链接”回发
- AstrBot 主动消息 `send_message()`

### 暂未完整支持

- Synology Chat 交互式按钮回调的完整闭环
- 本地图片 / 本地文件直接上传（Synology Chat 外部接口更适合 `file_url` 远程地址）
- 在机器人独立会话中稳定主动回传富媒体（如直接图片卡片 / `file_url`）
- 非统一 Webhook 模式下的独立内置 HTTP Server

## Synology Chat 机器人能力边界说明

根据 Synology Chat 官方说明，**机器人只能在“机器人”分页下建立独立对话，无法加入群组对话或频道**。

这意味着本适配器不能简单套用一般 IM 平台的“群 / 私聊 + 主动定向发送”模型，应按更保守的方式理解 Synology Chat 机器人能力：

- 更适合：接收机器人会话中的 webhook 请求，并同步返回文本结果
- 不应默认假设：可以像普通 IM 账号一样，按 `user_id` / `channel_id` 稳定主动补发消息
- 特别是图片场景中，即使 AstrBot 已拿到图片 URL，Synology Chat 也可能因为缺少可用 target 或机器人会话限制而拒绝投递

因此，当前实现对图片结果采取了更稳妥的兼容策略：

- **不再优先主动发送 `file_url` 图片**
- **统一降级为文本消息，并附上图片链接**

这样做的目的不是追求最佳展示效果，而是优先保证在 Synology Chat 机器人独立会话中“至少能稳定把结果送达用户”。

## 兼容性说明

本实现参考了：

- AstrBot 最新平台适配器文档
- AstrBot 仓库现有平台适配器结构
- Synology Chat 整合功能文档中关于 `payload`、`channel_id`、`user_id`、`trigger_word`、`attachments`、`SYNO.Chat.External` 的说明

由于 Synology 官方文档页面是面向整合配置的说明页，部分细节没有像 OpenAPI 那样完整列出，因此这里采取了**工程上可落地的保守实现**：

- 接收侧兼容 `JSON` / `form` / `payload=JSON字符串`
- 发送侧使用 `SYNO.Chat.External` + `method=incoming` 的常见用法
- 文本场景尽量复用 webhook 同步回包
- 图片场景默认降级为“文本 + 图片链接”，避免因主动富媒体投递失败而无响应

## 部署建议

1. 先启用插件并注册适配器
2. 在 AstrBot 中创建 `synochat_adapter` 平台实例
3. 开启统一 Webhook
4. 将 Webhook 地址填到 Synology Chat 的传出 Webhook / 斜线指令中
5. 在 Synology Chat 中发消息测试

## 安装时的目录要求

请确保最终目录结构严格如下：

```text
data/plugins/synochat_adapter/
├── assets/
│   └── synology-chat.svg
├── metadata.yaml
├── main.py
├── synology_chat_adapter.py
├── synology_chat_event.py
└── README.md
```

不要只复制其中某一个 `.py` 文件，也不要把这些文件直接丢到 `data/plugins/` 根目录。

如果你需要，我下一步还可以继续帮你补：

- 插件清单文件（若你当前 AstrBot 安装方式需要）
- 交互式按钮 `attachments/actions` 回调
- 独立 HTTP Server 模式
- 更完整的群组 / 私聊路由策略