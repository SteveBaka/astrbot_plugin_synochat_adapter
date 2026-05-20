from __future__ import annotations

import asyncio
import hmac
import json
import time
import urllib.parse
from collections.abc import Coroutine
from typing import Any, Optional

import aiohttp
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
from .synology_chat_helpers import (
    build_image_link_text,
    extract_image_url,
    log_standalone_webhook_info,
    log_webhook_info,
    normalize_synology_token,
    normalize_target_value,
    parse_synology_chatbot_url,
    safe_int,
    safe_str,
)


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

    _EXPIRED_SESSION_TTL: float = 120.0
    _CLEANUP_INTERVAL: float = 60.0

    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.settings = platform_settings
        self._http_session: aiohttp.ClientSession | None = None

        configured_base_value = safe_str(platform_config.get("base_url")).strip()
        self.incoming_webhook_url = safe_str(
            platform_config.get("incoming_webhook_url")
        ).strip()

        parsed_chatbot = parse_synology_chatbot_url(configured_base_value)
        if not parsed_chatbot:
            parsed_chatbot = parse_synology_chatbot_url(self.incoming_webhook_url)

        self.chat_api = safe_str(parsed_chatbot.get("api") or "SYNO.Chat.External")
        self.chat_method = safe_str(parsed_chatbot.get("method") or "incoming")
        self.chat_version = safe_int(parsed_chatbot.get("version")) or 2

        configured_base_url = configured_base_value.rstrip("/")
        if configured_base_url and "/webapi/entry.cgi" in configured_base_url:
            configured_base_url = ""
        parsed_base_url = safe_str(parsed_chatbot.get("base_url")).rstrip("/")
        self.base_url = configured_base_url or parsed_base_url

        configured_bot_token = normalize_synology_token(
            platform_config.get("bot_token")
        )
        parsed_token = normalize_synology_token(parsed_chatbot.get("token"))
        configured_outgoing_token = normalize_synology_token(
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
        self.timeout_reply_text = safe_str(
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

        self._log_config_info(
            configured_base_value,
            configured_base_url,
            configured_bot_token,
            parsed_base_url,
            parsed_token,
        )

    def _log_config_info(
        self,
        configured_base_value: str,
        configured_base_url: str,
        configured_bot_token: str,
        parsed_base_url: str,
        parsed_token: str,
    ) -> None:
        has_url = configured_base_value or self.incoming_webhook_url
        if has_url and parsed_token and not configured_bot_token:
            logger.info("[SynologyChatAdapter] 已从配置中自动提取 bot_token。")
        if has_url and parsed_base_url and not configured_base_url:
            logger.info(
                "[SynologyChatAdapter] 已从配置中自动提取 base_url=%s",
                parsed_base_url,
            )
        if has_url:
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

    def _ensure_http_session(self) -> aiohttp.ClientSession:
        if self._http_session is None or self._http_session.closed:
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            self._http_session = aiohttp.ClientSession(timeout=timeout)
        return self._http_session

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="synochat_adapter",
            description="Synology Chat 平台适配器",
            id=safe_str(self.config.get("id") or "synochat_adapter"),
            support_proactive_message=True,
        )

    def run(self) -> Coroutine[Any, Any, None]:
        async def _runner() -> None:
            if self.unified_webhook():
                webhook_uuid = safe_str(self.config.get("webhook_uuid"))
                if webhook_uuid:
                    log_webhook_info(webhook_uuid)
                await self._shutdown_event.wait()
            else:
                log_standalone_webhook_info(self.webhook_port)
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
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
            self._http_session = None

    async def _standalone_shutdown_trigger(self) -> None:
        await self._shutdown_event.wait()

    def _cleanup_expired_sessions_if_needed(self) -> None:
        now = time.time()
        if now - self._expired_session_last_cleanup < self._CLEANUP_INTERVAL:
            return
        self._expired_session_last_cleanup = now
        expired = [
            sid
            for sid, ts in self._expired_webhook_sessions.items()
            if now - ts > self._EXPIRED_SESSION_TTL
        ]
        for sid in expired:
            self._expired_webhook_sessions.pop(sid, None)

    def _create_standalone_webhook_app(self) -> quart.Quart:
        if self._standalone_webhook_app is not None:
            return self._standalone_webhook_app

        app = quart.Quart(__name__)

        async def _handle_request() -> Any:
            if quart.request.method == "GET":
                return {
                    "success": True,
                    "message": "Synology Chat adapter webhook is running",
                }
            return await self.webhook_callback(quart.request)

        app.add_url_rule("/", view_func=_handle_request, methods=["GET", "POST"])
        app.add_url_rule(
            "/webhook/synology-chat",
            view_func=_handle_request,
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
        session = self._ensure_http_session()
        try:
            async with session.post(url, json=payload) as resp:
                raw = await resp.text()
                if not raw:
                    return {"success": True}
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return {"success": True, "raw": raw}
        except aiohttp.ClientResponseError as exc:
            logger.error(
                "[SynologyChatAdapter] HTTPError when sending message: %s %s",
                exc.status,
                exc.message,
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
            image_url = await extract_image_url(comp)
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
            payload["text"] = build_image_link_text(text, image_urls)
            logger.debug(
                "[SynologyChatAdapter] downgrade image to text links text=%s image_urls=%s",
                payload.get("text"),
                image_urls,
            )
        elif text:
            payload["text"] = text

        target_id = safe_str(getattr(session, "session_id", ""))
        message_type = getattr(session, "message_type", None)
        if message_type == MessageType.FRIEND_MESSAGE and (
            target_id or fallback_sender_id
        ):
            payload["user_ids"] = [
                normalize_target_value(target_id or fallback_sender_id)
            ]
        elif target_id or fallback_group_id:
            payload["channel_id"] = normalize_target_value(
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
        session_id = safe_str(getattr(session, "session_id", ""))
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
        session_id = safe_str(getattr(session, "session_id", ""))
        logger.debug(
            "[SynologyChatAdapter] send_by_session session_id=%s message_type=%s",
            session_id,
            getattr(session, "message_type", None),
        )
        payload = await self.build_payload_from_chain(session, message_chain)

        self._cleanup_expired_sessions_if_needed()

        expired_at = self._expired_webhook_sessions.get(session_id)
        if expired_at is not None:
            if time.time() - expired_at <= self._EXPIRED_SESSION_TTL:
                logger.warning(
                    "[SynologyChatAdapter] webhook session_id=%s 已超时结束，忽略后续迟到回复。",
                    session_id,
                )
                return
            self._expired_webhook_sessions.pop(session_id, None)

        pending_replies = self._pending_webhook_replies.get(session_id, [])
        if pending_replies:
            future = pending_replies.pop(0)
            if not pending_replies:
                self._pending_webhook_replies.pop(session_id, None)
            webhook_payload = {
                k: v for k, v in payload.items() if k not in ("user_ids", "channel_id")
            }
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
        channel_id = safe_str(data.get("channel_id"))
        user_id = safe_str(data.get("user_id"))
        username = safe_str(data.get("username") or user_id or "synology_user")
        text = safe_str(data.get("text"))
        post_id = safe_str(data.get("post_id"))
        timestamp = data.get("timestamp")

        abm.self_id = safe_str(self.meta().id)
        abm.sender = MessageMember(user_id=user_id or username, nickname=username)
        abm.message_id = post_id or f"synology-{user_id}-{timestamp}"
        abm.raw_message = data
        abm.message_str = text
        abm.message = [Plain(text=text)] if text else []
        safe_timestamp = safe_int(timestamp)
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

        json_data = await self._try_parse_json(request)
        if json_data:
            data.update(json_data)

        form_data = await self._try_parse_form(request)
        if form_data:
            data.update(form_data)

        if isinstance(data.get("payload"), str):
            try:
                payload_data = json.loads(data["payload"])
                if isinstance(payload_data, dict):
                    data.update(payload_data)
            except json.JSONDecodeError:
                pass

        if not data:
            raw_data = await self._try_parse_raw(request)
            if raw_data:
                data.update(raw_data)

        return data

    async def _try_parse_json(self, request: Any) -> dict[str, Any] | None:
        try:
            json_data = await request.get_json(silent=True)
            if isinstance(json_data, dict):
                return json_data
        except Exception as exc:
            logger.debug("[SynologyChatAdapter] failed to parse JSON body: %s", exc)
        return None

    async def _try_parse_form(self, request: Any) -> dict[str, Any] | None:
        try:
            form_data = await request.form
            if form_data:
                if hasattr(form_data, "to_dict"):
                    return form_data.to_dict(flat=True)
                return dict(form_data)
        except Exception as exc:
            logger.debug("[SynologyChatAdapter] failed to parse form data: %s", exc)
        return None

    async def _try_parse_raw(self, request: Any) -> dict[str, Any] | None:
        try:
            raw = await request.get_data()
            if not raw:
                return None
            text = raw.decode("utf-8", errors="ignore")
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                qs = urllib.parse.parse_qs(text, keep_blank_values=True)
                result = {k: v[0] if v else "" for k, v in qs.items()}
                if isinstance(result.get("payload"), str):
                    try:
                        payload_data = json.loads(result["payload"])
                        if isinstance(payload_data, dict):
                            result.update(payload_data)
                    except json.JSONDecodeError:
                        pass
                return result
        except Exception as exc:
            logger.debug(
                "[SynologyChatAdapter] failed to parse raw request body: %s", exc
            )
        return None

    def _verify_incoming_token(self, data: dict[str, Any]) -> bool:
        if not self.verify_token:
            return True
        incoming_token = safe_str(data.get("token"))
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

        text = safe_str(data.get("text"))
        trigger_word = safe_str(data.get("trigger_word"))
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
            self._remove_pending_future(message.session_id, reply_future)
            return reply_payload
        except asyncio.TimeoutError:
            logger.debug(
                "[SynologyChatAdapter] webhook session_id=%s reply timeout after %ss, fallback ack",
                message.session_id,
                self.webhook_reply_timeout,
            )
            self._remove_pending_future(message.session_id, reply_future)
            self._expired_webhook_sessions[message.session_id] = time.time()
            if self.timeout_reply_text:
                return {"text": self.timeout_reply_text}
            return {"success": True}

    def _remove_pending_future(
        self, session_id: str, future: asyncio.Future
    ) -> None:
        pending = self._pending_webhook_replies.get(session_id, [])
        if future in pending:
            pending.remove(future)
            if not pending:
                self._pending_webhook_replies.pop(session_id, None)
