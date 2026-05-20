# Changelog

## [0.2.0] - 2026-05-20

### Changed

- **重构 HTTP 客户端**：将 `urllib.request` 替换为 `aiohttp`，实现真正的异步 HTTP 请求，避免阻塞事件循环
- **提取工具函数**：将模块级工具函数提取到 `synology_chat_helpers.py`，改善代码组织与可维护性
- **简化请求解析**：将 `_parse_request_data` 拆分为 `_try_parse_json`、`_try_parse_form`、`_try_parse_raw` 三个独立方法，降低复杂度
- **改善流式消息**：将标点符号集合提取为模块级常量 `_STREAMING_FLUSH_CHARS`，使用 `frozenset` 提升查找效率
- **提取配置日志**：将 `__init__` 中的日志输出逻辑提取为 `_log_config_info` 方法
- **HTTP 会话管理**：新增 `_ensure_http_session` 方法实现会话复用，在 `terminate()` 中正确关闭会话
- **统一常量管理**：将魔法数字 `120`、`60` 提取为类级常量 `_EXPIRED_SESSION_TTL`、`_CLEANUP_INTERVAL`
- **提取 Future 清理**：将重复的 Future 清理逻辑提取为 `_remove_pending_future` 方法
- **合并重复路由**：独立 Webhook 模式下两个路由处理函数合并为 `_handle_request`
- **添加 `__future__` 注解**：所有模块启用 `from __future__ import annotations` 以支持现代类型注解语法
- **添加类型提示**：事件类使用 `TYPE_CHECKING` 避免循环导入，为 `adapter` 和 `pending_reply` 添加精确类型

### Added

- 新增 `requirements.txt`，声明 `aiohttp` 和 `quart` 依赖
- 新增 `synology_chat_helpers.py` 模块，包含所有工具函数

### Fixed

- 更新 `.gitignore`，添加 `__pycache__/`、`*.py[cod]`、`.env`、`.venv/` 等 Python 标准忽略项

## [0.1.1] - 2026-04-14

### Added

- 新增 Synology Chat 平台适配器插件基础项目结构
- 新增 `synochat_adapter` 平台适配能力：
  - 支持接收 Synology Chat **传出 Webhook** 消息
  - 支持将 AstrBot 处理结果回发到 Synology Chat
  - 支持 AstrBot 主动调用 `send_message()` 发送消息
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
