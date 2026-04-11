# AstrBot Synology Chat 适配器

一个用于将 **Synology Chat** 接入 **AstrBot** 的平台适配器插件。

## 插件简介

本插件用于连接 AstrBot 与 Synology Chat：

- Synology Chat 通过 **传出 Webhook** 或 **斜线指令** 将消息发送到 AstrBot
- AstrBot 处理完成后，再通过 Synology Chat 机器人接口将结果回复到会话中

目前已支持基础文本消息收发，并支持将图片结果降级为图片链接回复。

## 插件信息

- 插件名：`astrbot_plugin_synochat_adapter`
- 适用平台：AstrBot
- 目标平台：Synology Chat

## 安装方式

请使用 **`.zip` 压缩包方式** 通过 AstrBot 本地安装插件。

> 注意：本地安装时**不需要手动解压**到 `data/plugins/` 目录，直接在 AstrBot 插件安装界面导入 `.zip` 文件即可。

## Synology Chat 配置

### 1. 创建机器人

在 Synology Chat 中创建机器人，并准备以下信息：

- Chat 服务地址，例如：`https://chat.example.com`
- Bot Token
- 或直接复制 Synology Chat 生成的完整 chatbot 链接（推荐）

常见链接格式如下：

```text
https://nas-ip:port/webapi/entry.cgi?api=SYNO.Chat.External&method=chatbot&version=2&token=%22YOUR_BOT_TOKEN%22
```

插件支持直接读取这条完整链接，并自动提取连接所需参数。

### 2. 配置传出 Webhook 或斜线指令

将 AstrBot 生成的 Webhook 地址填入 Synology Chat，例如：

```text
https://bot.example.com/api/platform/webhook/xxxxxxxx
```

你可以将它填写到：

- **传出 Webhook**
- **斜线指令**

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

1. 在 AstrBot 中通过 `.zip` 文件安装本插件
2. 重启或重载 AstrBot 插件
3. 在 AstrBot 中创建 `synochat_adapter` 平台实例
4. 开启统一 Webhook
5. 复制 AstrBot 生成的 Webhook 地址
6. 将该地址填回 Synology Chat 的传出 Webhook 或斜线指令配置
7. 在 Synology Chat 中发送消息测试

## 功能特性

- 接收 Synology Chat 传出 Webhook 消息
- 接收斜线指令数据
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

## 参考文档

- AstrBot 平台适配器开发文档
- AstrBot 平台适配器源码结构
- Synology Chat 整合功能文档