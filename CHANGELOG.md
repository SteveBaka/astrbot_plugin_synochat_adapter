# Changelog

## [0.1.1] - 2026-04-14

### Added

- 新增 Synology Chat 平台适配器插件基础项目结构
- 新增 `synochat_adapter` 平台适配能力：
  - 支持接收 Synology Chat **传出 Webhook** 消息
  - 支持将 AstrBot 处理结果回发到 Synology Chat
  - 支持 AstrBot 主动调用 `send_message()` 发送消息
- 新增 Synology Chat 图标资源：`assets/synology-chat.svg`
- 新增 `README.md` 使用说明文档，包含安装、配置、使用流程与参考资料

### Changed

- 调整插件安装说明：
  - 改为在 **AstrBot 插件市场** 中搜索 `astrbot_plugin_synochat_adapter` 安装
  - 补充“消息平台 → 新增适配器 → 选择 `synochat_adapter`”的操作路径
- 优化文档中的 Synology Chat 配置说明：
  - 优先推荐直接使用完整 chatbot 链接
  - 将 Chat 服务地址示例调整为默认 DSM 地址格式 `http(s)://nas-ip:port/`
- 优化使用说明，推荐在 Synology Chat 中优先使用普通文本命令

### Fixed

- 调整图片消息回复表现：
  - 去除图片回复前多余的 `[图片]` 文本
  - 保持以“文本 + 图片链接”的方式回传，降低兼容性问题

### Docs

- 补充普通文本命令使用提示：
  - 可使用 `help`、`ls` 等命令替代 `/help`、`/ls`
- 补充图片无法打开时的排查说明：
  - 可尝试配置 **对外可达的回调接口地址**
  - 建议填写公网可访问的 IP 或域名
  - 说明外部服务会通过 AstrBot 生成的回调链接（如文件下载链接）访问 AstrBot 后端的原理
- 为参考文档补充可直接访问的网址链接
