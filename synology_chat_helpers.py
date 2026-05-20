from __future__ import annotations

import asyncio
import urllib.parse
from typing import Any, Optional

from astrbot.api import logger

SYNOLOGY_IMAGE_PLACEHOLDER_TEXT = "[图片]"


def safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_synology_token(token: Any) -> str:
    value = safe_str(token).strip()
    if not value:
        return ""
    if len(value) >= 2 and (
        (value[0] == '"' and value[-1] == '"')
        or (value[0] == "'" and value[-1] == "'")
    ):
        value = value[1:-1].strip()
    return value


def parse_synology_chatbot_url(url: Any) -> dict[str, str]:
    raw_url = safe_str(url).strip()
    if not raw_url:
        return {}

    parsed = urllib.parse.urlparse(raw_url)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    token = normalize_synology_token((query.get("token") or [""])[0])
    base_url = ""
    if parsed.scheme and parsed.netloc:
        base_url = f"{parsed.scheme}://{parsed.netloc}"
    return {
        "base_url": base_url,
        "token": token,
        "api": safe_str((query.get("api") or [""])[0]),
        "method": safe_str((query.get("method") or [""])[0]),
        "version": safe_str((query.get("version") or [""])[0]),
    }


def normalize_target_value(value: Any) -> Any:
    int_value = safe_int(value)
    if int_value is not None:
        return int_value
    return safe_str(value)


async def maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return await value
    return value


async def extract_image_url(component: Any) -> str:
    candidates = [
        getattr(component, "url", None),
        getattr(component, "file", None),
        getattr(component, "image", None),
        getattr(component, "path", None),
    ]
    for candidate in candidates:
        value = safe_str(candidate).strip()
        if value.startswith(("http://", "https://")):
            return value

    register_to_file_service = getattr(component, "register_to_file_service", None)
    if callable(register_to_file_service):
        try:
            registered_url = await maybe_await(register_to_file_service())
            registered_value = safe_str(registered_url).strip()
            if registered_value.startswith(("http://", "https://")):
                logger.debug(
                    "[SynologyChatAdapter] image registered to file service: %s",
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


def build_image_link_text(text: str, image_urls: list[str]) -> str:
    normalized_text = text.strip()
    if not image_urls:
        return normalized_text

    lines: list[str] = []
    if normalized_text and normalized_text != SYNOLOGY_IMAGE_PLACEHOLDER_TEXT:
        lines.append(normalized_text)

    if len(image_urls) == 1:
        lines.append(f"图片链接：{image_urls[0]}")
    else:
        lines.append("图片链接：")
        lines.extend(f"{idx}. {url}" for idx, url in enumerate(image_urls, start=1))
    return "\n".join(lines).strip()


def log_webhook_info(webhook_uuid: str) -> None:
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


def log_standalone_webhook_info(port: int) -> None:
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
