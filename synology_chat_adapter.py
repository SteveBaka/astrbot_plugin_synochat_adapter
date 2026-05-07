import asyncio
import hmac
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

import quart
from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Image, Plain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.platform.register import register_platform_adapter

from .synology_chat_event import SynologyChatMessageEvent

_SYNOLOGY_IMAGE_PLACEHOLDER_TEXT = "[图片]"


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _normalize_synology_token(token: Any) -> str:
    value = _safe_str(token).strip()
    if not value:
        return ""
    if len(value) >= 2 and (
        (value[0] == '"' and value[-1] == '"') or (value[0] == "'" and value[-1] == "'")
    ):
        value = value[1:-1].strip()
    return value


def _parse_synology_chatbot_url(url: Any) -> dict[str, str]:
    raw_url = _safe_str(url).strip()
    if not raw_url:
        return {}

    parsed = urllib.parse.urlparse(raw_url)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    token = _normalize_synology_token((query.get("token") or [""])[0])
    base_url = ""
    if parsed.scheme and parsed.netloc:
        base_url = f"{parsed.scheme}://{parsed.netloc}"
    return {
        "base_url": base_url,
        "token": token,
        "api": _safe_str((query.get("api") or [""])[0]),
        "method": _safe_str((query.get("method") or [""])[0]),
        "version": _safe_str((query.get("version") or [""])[0]),
    }


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_target_value(value: Any) -> Any:
    int_value = _safe_int(value)
    if int_value is not None:
        return int_value
    return _safe_str(value)


async def _extract_image_url(component: Any) -> str:
    candidates = [
        getattr(component, "url", None),
        getattr(component, "file", None),
        getattr(component, "image", None),
        getattr(component, "path", None),
    ]
    for candidate in candidates:
        value = _safe_str(candidate).strip()
        if value.startswith(("http://", "https://")):
            return value

    register_to_file_service = getattr(component, "register_to_file_service", None)
    if callable(register_to_file_service):
        try:
            registered_url = await _maybe_await(register_to_file_service())
            registered_value = _safe_str(registered_url).strip()
            if registered_value.startswith(("http://", "https://")):
                logger.debug(
                    "[SynologyChatAdapter] image component registered to file service: %s",
                    registered_value,
                )
                return registered_value
            if registered_value:
                logger.debug(
                    "[SynologyChatAdapter] registered value is not a URL: %s",
                    registered_value,
                )
        except Exception as exc:
            logger.warning(
                "[SynologyChatAdapter] failed to register image to file service: %s",
                exc,
            )

    return ""


def _build_image_link_text(text: str, image_urls: list[str]) -> str:
    normalized_text = _safe_str(text).strip()
    if not image_urls:
        return normalized_text

    lines: list[str] = []
    if normalized_text and normalized_text != _SYNOLOGY_IMAGE_PLACEHOLDER_TEXT:
        lines.append(normalized_text)

    if len(image_urls) == 1:
        lines.append(f"图片链接：{image_urls[0]}")
    else:
        lines.append("图片链接：")
        lines.extend(f"{idx}. {url}" for idx, url in enumerate(image_urls, start=1))
    return "\n".join(lines).strip()


def _log_webhook_info(webhook_uuid: str) -> None:
    logger.info(
        "\n====================\n"
        "🔗 机器人平台 Synology Chat 已启用统一 Webhook 模式\n"
        "📍 Webhook 回调地址示例: \n"
        "   ➜  https://<your-astrbot-domain>:<对应端口>/api/platform/webhook/%s\n"
        "   ➜  http://<your-astrbot-domain>:<对应端口>/api/platform/webhook/%s\n"
        "   ➜  http://<your-ip>:6185/api/platform/webhook/%s\n"
        "====================\n",
        webhook_uuid,
        webhook_uuid,
        webhook_uuid,
    )


def _log_standalone_webhook_info(port: int) -> None:
    logger.info(
        "\n====================\n"
        "🔗 机器人平台 Synology Chat 已启用独立 Webhook 模式\n"
        "📍 请将 Synology Chat 的传出 Webhook 指向以下地址之一: \n"
        "   ➜  http://<your-astrbot-domain>:%s/\n"
        "   ➜  http://<your-astrbot-domain>:%s/webhook/synology-chat\n"
        "   ➜  http://<your-ip>:%s/webhook/synology-chat\n"
        "====================\n",
        port,
        port,
        port,
    )


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return await value
    return value


@register_platform_adapter(
    "synochat_adapter",
    "Synology Chat 平台适配器",
    default_config_tmpl={
        "base_url": "https://chat.example.com",
        "incoming_webhook_url": "",
        "bot_token": "",
        "outgoing_token": "",
        "request_timeout": 15,
        "webhook_reply_timeout": 0,
        "timeout_reply_text": "AstrBot 当前未生成回复，请检查模型配置或稍后重试。",
        "verify_token": True,
        "unified_webhook_mode": True,
        "webhook_port": 9876,
        "webhook_uuid": "",
    },
    adapter_display_name="Synology Chat",
    support_streaming_message=True,
    config_metadata={
        "base_url": {
            "description": "Synology Chat 服务地址",
            "type": "string",
            "hint": "可填写服务根地址，例如 https://chat.example.com；也可直接粘贴 Synology Chat 生成的 chatbot 完整 URL，适配器会自动提取地址与 token。",
        },
        "incoming_webhook_url": {
            "description": "ChatBot 完整链接",
            "type": "string",
            "hint": "可直接粘贴 Synology Chat 生成的 chatbot 完整 URL，适配器会自动提取地址与 token。",
            "secret": True,
            "invisible": True,
        },
        "bot_token": {
            "description": "Bot Token",
            "type": "string",
            "hint": "发送消息使用的 token；如果上方已填写完整链接，这里可留空。",
            "secret": True,
            "invisible": True,
        },
        "outgoing_token": {
            "description": "传出 Webhook Token",
            "type": "string",
            "hint": "用于校验 Synology Chat 回调请求；留空时默认使用 Bot Token。",
            "secret": True,
        },
        "request_timeout": {
            "description": "请求超时（秒）",
            "type": "int",
            "hint": "调用 Synology Chat API 时的超时时间。",
        },
        "webhook_reply_timeout": {
            "description": "Webhook 等待回复超时（秒）",
            "type": "int",
            "hint": "Synology Chat 回调后，等待 AstrBot 生成同步回复的最长时间；设为 0 或负数表示不做适配器内部超时限制。",
        },
        "timeout_reply_text": {
            "description": "Webhook 超时兜底回复",
            "type": "string",
            "hint": "当 AstrBot 在超时时间内未产生回复时，直接返回给 Synology Chat 的提示文本。",
        },
        "verify_token": {
            "description": "校验传入 Token",
            "type": "bool",
            "hint": "建议开启，避免未授权请求调用机器人。",
        },
        "unified_webhook_mode": {
            "description": "统一 Webhook 模式",
            "type": "bool",
            "hint": "建议开启，使用 AstrBot 统一 Webhook 入口。",
        },
        "webhook_port": {
            "description": "Webhook 监听端口",
            "type": "int",
            "hint": "关闭统一 Webhook 模式后生效，用于独立 webhook 服务监听端口，默认 9876。",
        },
        "webhook_uuid": {
            "description": "Webhook UUID",
            "type": "string",
            "hint": "统一 Webhook 模式下的平台 webhook 标识。",
        },
    },
)
class SynologyChatAdapter(Platform):
    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.settings = platform_settings
        configured_base_value = _safe_str(platform_config.get("base_url")).strip()
        self.incoming_webhook_url = _safe_str(
            platform_config.get("incoming_webhook_url")
        ).strip()

        parsed_chatbot = _parse_synology_chatbot_url(configured_base_value)
        if not parsed_chatbot:
            parsed_chatbot = _parse_synology_chatbot_url(self.incoming_webhook_url)

        self.chat_api = _safe_str(parsed_chatbot.get("api") or "SYNO.Chat.External")
        self.chat_method = _safe_str(parsed_chatbot.get("method") or "incoming")
        self.chat_version = _safe_int(parsed_chatbot.get("version")) or 2

        configured_base_url = configured_base_value.rstrip("/")
        if configured_base_url and "/webapi/entry.cgi" in configured_base_url:
            configured_base_url = ""
        parsed_base_url = _safe_str(parsed_chatbot.get("base_url")).rstrip("/")
        self.base_url = configured_base_url or parsed_base_url

        configured_bot_token = _normalize_synology_token(
            platform_config.get("bot_token")
        )
        parsed_token = _normalize_synology_token(parsed_chatbot.get("token"))
        configured_outgoing_token = _normalize_synology_token(
            platform_config.get("outgoing_token")
        )
        self.bot_token = (
            configured_bot_token or configured_outgoing_token or parsed_token
        )

        self.outgoing_token = (
            configured_outgoing_token or parsed_token or self.bot_token
        )
        self.request_timeout = int(platform_config.get("request_timeout", 15) or 15)
        self.webhook_reply_timeout = int(
            platform_config.get("webhook_reply_timeout", 0) or 0
        )
        self.timeout_reply_text = _safe_str(
            platform_config.get(
                "timeout_reply_text",
                "AstrBot 当前未生成回复，请检查模型配置或稍后重试。",
            )
        )
        self.verify_token = bool(platform_config.get("verify_token", True))
        self.webhook_port = int(platform_config.get("webhook_port", 9876) or 9876)
        self._shutdown_event = asyncio.Event()
        self._pending_webhook_replies: dict[str, list[asyncio.Future]] = {}
        self._expired_webhook_sessions: dict[str, float] = {}
        self._standalone_webhook_app: quart.Quart | None = None
        self._expired_session_last_cleanup: float = 0.0

        if (
            (configured_base_value or self.incoming_webhook_url)
            and parsed_token
            and not configured_bot_token
        ):
            logger.info("[SynologyChatAdapter] 已从配置中自动提取 bot_token。")
        if (
            (configured_base_value or self.incoming_webhook_url)
            and parsed_base_url
            and not configured_base_url
        ):
            logger.info(
                "[SynologyChatAdapter] 已从配置中自动提取 base_url=%s",
                parsed_base_url,
            )
        if configured_base_value or self.incoming_webhook_url:
            logger.info(
                "[SynologyChatAdapter] 发送接口参数：api=%s method=%s version=%s",
                self.chat_api,
                self.chat_method,
                self.chat_version,
            )
        if self.webhook_reply_timeout > 10:
            logger.warning(
                "[SynologyChatAdapter] webhook_reply_timeout=%s 秒可能超过 Synology Chat 可接受的 webhook 等待时间，"
                "建议调整到 8~10 秒以内。",
                self.webhook_reply_timeout,
            )
        elif self.webhook_reply_timeout <= 0:
            logger.warning(
                "[SynologyChatAdapter] webhook_reply_timeout=%s，已关闭适配器内部超时限制；"
                "若 Synology Chat 或反向代理存在请求超时，仍可能由对端先断开连接。",
                self.webhook_reply_timeout,
            )

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="synochat_adapter",
            description="Synology Chat 平台适配器",
            id=_safe_str(self.config.get("id") or "synochat_adapter"),
            support_proactive_message=True,
        )

    def run(self):
        async def _runner() -> None:
            if self.unified_webhook():
                webhook_uuid = _safe_str(self.config.get("webhook_uuid"))
                if webhook_uuid:
                    _log_webhook_info(webhook_uuid)
                await self._shutdown_event.wait()
            else:
                _log_standalone_webhook_info(self.webhook_port)
                app = self._create_standalone_webhook_app()
                try:
                    await app.run_task(
                        host="0.0.0.0",
                        port=self.webhook_port,
                        shutdown_trigger=self._standalone_shutdown_trigger,
                    )
                except Exception as exc:
                    logger.error(
                        "[SynologyChatAdapter] standalone webhook server exited unexpectedly: %s",
                        exc,
                        exc_info=True,
                    )
                    raise

        return _runner()

    async def terminate(self) -> None:
        self._shutdown_event.set()

    async def _standalone_shutdown_trigger(self) -> None:
        await self._shutdown_event.wait()

    def _cleanup_expired_sessions_if_needed(self) -> None:
        now = time.time()
        if now - self._expired_session_last_cleanup < 60:
            return
        self._expired_session_last_cleanup = now
        expired = [
            sid for sid, ts in self._expired_webhook_sessions.items() if now - ts > 120
        ]
        for sid in expired:
            self._expired_webhook_sessions.pop(sid, None)

    def _create_standalone_webhook_app(self) -> quart.Quart:
        if self._standalone_webhook_app is not None:
            return self._standalone_webhook_app

        app = quart.Quart(__name__)

        async def _handle_root() -> Any:
            if quart.request.method == "GET":
                return {
                    "success": True,
                    "message": "Synology Chat adapter webhook is running",
                }
            return await self.webhook_callback(quart.request)

        async def _handle_webhook() -> Any:
            if quart.request.method == "GET":
                return {
                    "success": True,
                    "message": "Synology Chat adapter webhook is running",
                }
            return await self.webhook_callback(quart.request)

        app.add_url_rule("/", view_func=_handle_root, methods=["GET", "POST"])
        app.add_url_rule(
            "/webhook/synology-chat",
            view_func=_handle_webhook,
            methods=["GET", "POST"],
        )
        self._standalone_webhook_app = app
        return app

    def get_client(self) -> object:
        return self

    def _build_api_url(
        self,
        method: Optional[str] = None,
        version: Optional[int] = None,
    ) -> str:
        query = urllib.parse.urlencode(
            {
                "api": self.chat_api,
                "method": method or self.chat_method,
                "version": version or self.chat_version,
                "token": self.bot_token,
            }
        )
        return f"{self.base_url}/webapi/entry.cgi?{query}"

    async def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        def _request() -> dict[str, Any]:
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json; charset=utf-8"},
                method="POST",
            )
            context = ssl.create_default_context()
            with urllib.request.urlopen(
                req,
                timeout=self.request_timeout,
                context=context,
            ) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
                if not raw:
                    return {"success": True}
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return {"success": True, "raw": raw}

        try:
            return await asyncio.to_thread(_request)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
            logger.error(
                "[SynologyChatAdapter] HTTPError when sending message: %s %s",
                exc.code,
                detail,
            )
            raise
        except Exception as exc:
            logger.error(
                "[SynologyChatAdapter] Failed to call Synology Chat API: %s",
                exc,
                exc_info=True,
            )
            raise

    async def _chain_to_text(self, message_chain: MessageChain) -> str:
        parts: list[str] = []
        for comp in getattr(message_chain, "chain", []):
            if isinstance(comp, Plain):
                parts.append(comp.text)
            elif isinstance(comp, Image):
                continue
            else:
                comp_type = getattr(comp, "type", comp.__class__.__name__)
                parts.append(f"[{comp_type}]")
        return "".join(parts).strip()

    async def _collect_image_urls(self, message_chain: MessageChain) -> list[str]:
        image_urls: list[str] = []
        for comp in getattr(message_chain, "chain", []):
            if not isinstance(comp, Image):
                continue
            image_url = await _extract_image_url(comp)
            if image_url and image_url not in image_urls:
                image_urls.append(image_url)
        return image_urls

    async def build_payload_from_chain(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
        fallback_sender_id: str = "",
        fallback_group_id: str = "",
    ) -> dict[str, Any]:
        image_urls = await self._collect_image_urls(message_chain)
        text = await self._chain_to_text(message_chain)
        payload: dict[str, Any] = {}
        if image_urls:
            payload["text"] = _build_image_link_text(text, image_urls)
            logger.debug(
                "[SynologyChatAdapter] downgrade image message to text links text=%s image_urls=%s",
                payload.get("text"),
                image_urls,
            )
        elif text:
            payload["text"] = text

        target_id = _safe_str(getattr(session, "session_id", ""))
        message_type = getattr(session, "message_type", None)
        if message_type == MessageType.FRIEND_MESSAGE and (
            target_id or fallback_sender_id
        ):
            payload["user_ids"] = [
                _normalize_target_value(target_id or fallback_sender_id)
            ]
        elif target_id or fallback_group_id:
            payload["channel_id"] = _normalize_target_value(
                target_id or fallback_group_id
            )

        return payload

    async def build_webhook_reply_payload(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> dict[str, Any]:
        payload = await self.build_payload_from_chain(session, message_chain)
        payload.pop("user_ids", None)
        payload.pop("channel_id", None)
        logger.debug("[SynologyChatAdapter] webhook reply payload=%s", payload)
        return payload or {"text": ""}

    async def send_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.base_url:
            raise ValueError("Synology Chat base_url 未配置")
        if not self.bot_token:
            raise ValueError("Synology Chat bot_token 未配置")
        url = self._build_api_url()
        logger.debug("[SynologyChatAdapter] proactive send payload=%s", payload)
        result = await self._post_json(url, payload)
        logger.debug("[SynologyChatAdapter] send payload=%s result=%s", payload, result)
        return result

    async def send_proactive_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> dict[str, Any]:
        payload = await self.build_payload_from_chain(session, message_chain)
        session_id = _safe_str(getattr(session, "session_id", ""))
        message_type = getattr(session, "message_type", None)
        if message_type == MessageType.FRIEND_MESSAGE:
            payload.pop("user_ids", None)
            payload.pop("channel_id", None)
        logger.debug(
            "[SynologyChatAdapter] proactive-by-session payload=%s session_id=%s message_type=%s",
            payload,
            session_id,
            message_type,
        )
        return await self.send_payload(payload)

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        session_id = _safe_str(getattr(session, "session_id", ""))
        logger.debug(
            "[SynologyChatAdapter] send_by_session session_id=%s message_type=%s",
            session_id,
            getattr(session, "message_type", None),
        )
        payload = await self.build_payload_from_chain(session, message_chain)

        self._cleanup_expired_sessions_if_needed()

        expired_at = self._expired_webhook_sessions.get(session_id)
        if expired_at is not None:
            if time.time() - expired_at <= 120:
                logger.warning(
                    "[SynologyChatAdapter] webhook session_id=%s 已超时结束，忽略后续迟到回复，避免错误走主动发送分支。",
                    session_id,
                )
                return
            self._expired_webhook_sessions.pop(session_id, None)

        pending_replies = self._pending_webhook_replies.get(
            session_id,
            [],
        )
        if pending_replies:
            future = pending_replies.pop(0)
            if not pending_replies:
                self._pending_webhook_replies.pop(
                    session_id,
                    None,
                )
            webhook_payload = dict(payload)
            webhook_payload.pop("user_ids", None)
            webhook_payload.pop("channel_id", None)
            if not future.done():
                future.set_result(webhook_payload or {"text": ""})
            logger.debug(
                "[SynologyChatAdapter] use webhook direct reply payload=%s",
                webhook_payload,
            )
            await super().send_by_session(session, message_chain)
            return

        await self.send_payload(payload)
        await super().send_by_session(session, message_chain)

    def _build_message(self, data: dict[str, Any]) -> AstrBotMessage:
        abm = AstrBotMessage()
        channel_id = _safe_str(data.get("channel_id"))
        user_id = _safe_str(data.get("user_id"))
        username = _safe_str(data.get("username") or user_id or "synology_user")
        text = _safe_str(data.get("text"))
        post_id = _safe_str(data.get("post_id"))
        timestamp = data.get("timestamp")

        abm.self_id = _safe_str(self.meta().id)
        abm.sender = MessageMember(user_id=user_id or username, nickname=username)
        abm.message_id = post_id or f"synology-{user_id}-{timestamp}"
        abm.raw_message = data
        abm.message_str = text
        abm.message = [Plain(text=text)] if text else []
        safe_timestamp = _safe_int(timestamp)
        if safe_timestamp is not None:
            abm.timestamp = safe_timestamp

        if channel_id:
            abm.type = MessageType.GROUP_MESSAGE
            abm.group_id = channel_id
            abm.session_id = channel_id
        else:
            abm.type = MessageType.FRIEND_MESSAGE
            abm.session_id = user_id or username

        return abm

    async def handle_msg(
        self,
        message: AstrBotMessage,
        pending_reply: Optional[asyncio.Future] = None,
    ) -> None:
        event = SynologyChatMessageEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            adapter=self,
            pending_reply=pending_reply,
        )
        payload = message.raw_message if isinstance(message.raw_message, dict) else {}
        event.set_extra("trigger_word", payload.get("trigger_word"))
        event.set_extra("channel_name", payload.get("channel_name"))
        event.set_extra("synology_payload", payload)
        self.commit_event(event)

    async def _parse_request_data(self, request: Any) -> dict[str, Any]:
        data: dict[str, Any] = {}

        try:
            json_data = await _maybe_await(request.get_json(silent=True))
            if isinstance(json_data, dict):
                data.update(json_data)
        except Exception as exc:
            logger.debug("[SynologyChatAdapter] failed to parse JSON body: %s", exc)

        try:
            form_data = await _maybe_await(request.form)
            if form_data:
                if hasattr(form_data, "to_dict"):
                    data.update(form_data.to_dict(flat=True))
                else:
                    data.update(dict(form_data))
        except Exception as exc:
            logger.debug("[SynologyChatAdapter] failed to parse form data: %s", exc)

        if isinstance(data.get("payload"), str):
            try:
                payload_data = json.loads(data["payload"])
                if isinstance(payload_data, dict):
                    data.update(payload_data)
            except json.JSONDecodeError:
                pass

        if not data:
            try:
                raw = await _maybe_await(request.get_data())
                if raw:
                    text = raw.decode("utf-8", errors="ignore")
                    try:
                        parsed = json.loads(text)
                        if isinstance(parsed, dict):
                            data.update(parsed)
                    except json.JSONDecodeError:
                        qs = urllib.parse.parse_qs(text, keep_blank_values=True)
                        for key, value in qs.items():
                            data[key] = value[0] if value else ""
                        if isinstance(data.get("payload"), str):
                            try:
                                payload_data = json.loads(data["payload"])
                                if isinstance(payload_data, dict):
                                    data.update(payload_data)
                            except json.JSONDecodeError:
                                pass
            except Exception as exc:
                logger.debug(
                    "[SynologyChatAdapter] failed to parse raw request body: %s", exc
                )

        return data

    def _verify_incoming_token(self, data: dict[str, Any]) -> bool:
        if not self.verify_token:
            return True
        incoming_token = _safe_str(data.get("token"))
        if not incoming_token or not self.outgoing_token:
            return False
        return hmac.compare_digest(incoming_token, self.outgoing_token)

    async def webhook_callback(self, request: Any) -> Any:
        data = await self._parse_request_data(request)
        logger.debug("[SynologyChatAdapter] webhook payload=%s", data)

        if not data:
            return {"success": False, "error": "empty payload"}, 400

        if not self._verify_incoming_token(data):
            return {"success": False, "error": "invalid token"}, 403

        text = _safe_str(data.get("text"))
        trigger_word = _safe_str(data.get("trigger_word"))
        if trigger_word and text.startswith(trigger_word):
            text = text[len(trigger_word) :].strip()
            data["text"] = text

        message = self._build_message(data)
        reply_future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending_webhook_replies.setdefault(message.session_id, []).append(
            reply_future
        )
        await self.handle_msg(message, pending_reply=reply_future)
        try:
            if self.webhook_reply_timeout <= 0:
                reply_payload = await reply_future
            else:
                reply_payload = await asyncio.wait_for(
                    reply_future,
                    timeout=self.webhook_reply_timeout,
                )
            pending_replies = self._pending_webhook_replies.get(message.session_id, [])
            if reply_future in pending_replies:
                pending_replies.remove(reply_future)
                if not pending_replies:
                    self._pending_webhook_replies.pop(message.session_id, None)
            return reply_payload
        except asyncio.TimeoutError:
            logger.debug(
                "[SynologyChatAdapter] webhook session_id=%s reply timeout after %ss, fallback ack",
                message.session_id,
                self.webhook_reply_timeout,
            )
            pending_replies = self._pending_webhook_replies.get(message.session_id, [])
            if reply_future in pending_replies:
                pending_replies.remove(reply_future)
                if not pending_replies:
                    self._pending_webhook_replies.pop(message.session_id, None)
            self._expired_webhook_sessions[message.session_id] = time.time()
            if self.timeout_reply_text:
                return {"text": self.timeout_reply_text}
            return {"success": True}
