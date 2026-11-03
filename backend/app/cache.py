"""Optional answer cache. The database, not Redis, owns learning evidence."""

import hashlib
import json
import logging
import os
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


def answer_key(question: str, documents: list[dict], provider: dict) -> str:
    # Any note addition, edit, or deletion changes the key. Only a digest enters Redis.
    payload = {
        "question": question.strip(),
        "documents": sorted(
            [{"id": doc["id"], "title": doc["title"], "content": doc["content"],
              "version": doc.get("version", 1)} for doc in documents],
            key=lambda item: str(item["id"]),
        ),
        "provider": provider,
        "endpoint": os.getenv("AI_BASE_URL", "https://api.openai.com/v1"),
        "schema": 2,
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return "doknow:answer:" + hashlib.sha256(serialized).hexdigest()


class AnswerCache:
    def __init__(self, url: str | None = None):
        self.client = Redis.from_url(
            url, decode_responses=True, socket_connect_timeout=0.4,
            socket_timeout=0.4, retry_on_timeout=False,
        ) if url else None

    async def get(self, key: str) -> dict | None:
        if self.client is None:
            return None
        try:
            raw = await self.client.get(key)
            if raw:
                value = json.loads(raw)
                if isinstance(value, dict) and isinstance(value.get("answer"), str) and isinstance(value.get("sources"), list):
                    return value
        except (RedisError, OSError, ValueError, TypeError):
            logger.debug("Optional knowledge cache unavailable; reading database-backed materials.")
        return None

    async def put(self, key: str, value: dict[str, Any]) -> None:
        if self.client is None:
            return
        try:
            await self.client.set(key, json.dumps(value, ensure_ascii=False), ex=600)
        except (RedisError, OSError, ValueError, TypeError):
            logger.debug("Optional knowledge cache write unavailable.")

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aclose()
