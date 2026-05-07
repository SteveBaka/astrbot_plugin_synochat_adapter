# AstrBot Synology Chat 适配器

一个用于将 **Synology Chat** 接入 **AstrBot** 的平台适配器插件。

> 适用于希望通过 **Synology Chat 机器人 / Webhook** 将消息接入 AstrBot 的场景。

## 插件简介

本插件用于连接 AstrBot 与 Synology Chat：

- Synology Chat 通过 **传出 Webhook** 将消息发送到 AstrBot
- AstrBot 处理完成后，再通过 Synology Chat 机器人接口将结果回复到会话中

目前已支持基础文本消息收发，并支持将图片结果降级为图片链接回复。

## 插件信息

- 插件名：`astrbot_plugin_synochat_adapter`
- 适用平台：AstrBot
- 目标平台：Synology Chat

## 安装方式

请在 **AstrBot 插件市场** 中搜索插件名 **`astrbot_plugin_synochat_adapter`**，然后直接安装本插件。

> 建议直接通过插件市场安装，以便后续管理与更新。

安装完成后，前往 **消息平台** → **新增适配器** → 选择 **synochat_adapter**。

> 如果列表中没有出现该适配器，请先尝试**重启 AstrBot**，或检查插件是否已正确安装并启用。

## Synology Chat 配置

### 1. 创建机器人

在 Synology Chat 中创建机器人，并准备以下信息：

- 直接复制 Synology Chat 生成的完整 chatbot 链接（推荐）
- Chat 服务地址，通常可以使用默认的 Synology DSM 页面地址：`http(s)://nas-ip:port/`
- Bot Token

常见链接格式如下：

```text
https://nas-ip:port/webapi/entry.cgi?api=SYNO.Chat.External&method=chatbot&version=2&token=%22YOUR_BOT_TOKEN%22
```

插件支持直接读取这条完整链接，并自动提取连接所需参数。

### 2. 配置传出 Webhook

将 AstrBot 生成的 Webhook 地址填入 Synology Chat，例如：

```text
https://bot.example.com/api/platform/webhook/xxxxxxxx
```

你可以将它填写到：

- **传出 Webhook**

## AstrBot 配置

在 AstrBot 中新增平台时，可参考以下配置：

```json
{
  "id": "synology_chat",
  "type": "synochat_adapter",
  "enable": true,
  "incoming_webhook_url": "https://nas-ip:port/webapi/entry.cgi?api=SYNO.Chat.External&method=chatbot&version=2&token=%22YOUR_BOT_TOKEN%22",
  "outgoing_token": "",
  "verify_token": true,
  "unified_webhook_mode": true
}
```

### 常用配置项

- `incoming_webhook_url`：Synology Chat 提供的完整 chatbot 链接
- `outgoing_token`：用于校验 Synology Chat 的回调请求，如未单独设置可留空
- `verify_token`：建议开启
- `unified_webhook_mode`：建议开启

> 一般情况下，只填写 `incoming_webhook_url` 即可。

## 使用步骤

1. 在 AstrBot 插件市场中搜索 `astrbot_plugin_synochat_adapter`
2. 安装本插件并重启或重载 AstrBot 插件
3. 前往 **消息平台** → **新增适配器** → 选择 `synochat_adapter`
4. 在 AstrBot 中完成平台实例配置
5. 开启统一 Webhook
6. 复制 AstrBot 生成的 Webhook 地址
7. 将该地址填回 Synology Chat 的传出 Webhook 配置
8. 在 Synology Chat 中发送消息测试

> 由于斜线指令配置与使用相对更繁琐，目前更建议直接使用普通文本命令。
>
> 例如，可以使用 `help`、`ls` 等命令，来替代原有的 `/help`、`/ls` 指令。

## 功能特性

- 接收 Synology Chat 传出 Webhook 消息
- 文本消息回复
- 图片消息以“文本 + 图片链接”形式回复
- 支持 AstrBot 主动调用 `send_message()`

## 当前限制

- 暂不支持完整的交互式按钮回调
- 暂不支持本地图片 / 本地文件直接上传到 Synology Chat
- 图片消息目前以链接形式返回
- 更推荐在统一 Webhook 模式下使用

## 补充说明

根据 Synology Chat 机器人的使用方式，本插件当前优先保证文本与基础回复的稳定性，因此图片结果会以“图片链接”的方式返回，而不是直接作为富媒体消息发送。

> 如果遇到**图片链接可以收到但无法打开**的情况，可以尝试在 AstrBot 中配置 **对外可达的回调接口地址**。
>
> 这里建议填写一个**公网可以访问的 IP 或域名**，让 Synology Chat 或其他外部服务能够访问 AstrBot 生成的回调链接。
>
> 该功能的原理是：外部服务可能会通过 AstrBot 生成的回调链接（例如**文件下载链接**）访问 AstrBot 后端；如果 AstrBot 当前对外返回的是内网地址、局域网地址或外部无法访问的地址，那么 Synology Chat 中的图片链接就可能出现无法打开的情况。
>
> 因此，在这类场景下，将“对外可达的回调接口地址”配置为**公网可访问地址**，通常可以改善图片、文件等链接无法访问的问题。

## 安全说明

本插件调用的 Synology Chat API 要求将 Bot Token 作为 URL 查询参数传输（这是 Synology Chat API 的设计要求）。这意味着 token 可能出现在 HTTP 访问日志、代理日志等位置。

**建议：**

- 确保 AstrBot 与 Synology Chat 之间通过 **HTTPS** 通信
- 在反向代理或网志层面做好日志脱敏，避免 token 泄露

## 参考文档

- [AstrBot 平台适配器开发文档](https://docs.astrbot.app/dev/plugin-platform-adapter.html)
- [AstrBot 平台适配器源码结构](https://github.com/AstrBotDevs/AstrBot/tree/master/astrbot/core/platform)
- [Synology Chat 整合功能文档](https://kb.synology.com/zh-tw/DSM/help/Chat/chat_integration?version=7)