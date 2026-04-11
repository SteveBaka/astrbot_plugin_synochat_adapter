import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Image, Plain


def _message_chain_has_image(message: MessageChain) -> bool:
    return any(isinstance(comp, Image) for comp in getattr(message, "chain", []))


class SynologyChatMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str: str,
        message_obj: Any,
        platform_meta: Any,
        session_id: str,
        adapter: Any,
        pending_reply: Any = None,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.adapter = adapter
        self.pending_reply = pending_reply

    async def send(self, message: MessageChain) -> None:
        if self.pending_reply is not None and not self.pending_reply.done():
            if _message_chain_has_image(message):
                await self.adapter.send_proactive_by_session(self.session, message)
                self.pending_reply.set_result({"text": ""})
            else:
                payload = await self.adapter.build_webhook_reply_payload(self.session, message)
                self.pending_reply.set_result(payload)
        else:
            await self.adapter.send_by_session(self.session, message)
        await super().send(message)

    async def send_streaming(
        self,
        generator: AsyncGenerator,
        use_fallback: bool = False,
    ) -> None:
        if not use_fallback:
            merged = None
            async for chain in generator:
                if merged is None:
                    merged = chain
                else:
                    merged.chain.extend(chain.chain)
            if merged is not None:
                merged.squash_plain()
                await self.send(merged)
            return await super().send_streaming(generator, use_fallback)

        buffer = ""
        async for chain in generator:
            if not isinstance(chain, MessageChain):
                continue
            for comp in chain.chain:
                if isinstance(comp, Plain):
                    buffer += comp.text
                    if any(p in buffer for p in "。？！!?.;；\n"):
                        await self.send(MessageChain([Plain(buffer)]))
                        buffer = ""
                        await asyncio.sleep(0.3)
                elif isinstance(comp, Image):
                    if buffer.strip():
                        await self.send(MessageChain([Plain(buffer)]))
                        buffer = ""
                    await self.send(MessageChain([comp]))
                    await asyncio.sleep(0.3)

        if buffer.strip():
            await self.send(MessageChain([Plain(buffer)]))
