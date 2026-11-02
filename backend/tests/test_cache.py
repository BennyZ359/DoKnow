import pytest
from redis.exceptions import ConnectionError

from app.cache import AnswerCache, answer_key


def test_cache_keys_track_document_changes_and_model():
    docs = [{"id": "one", "title": "笔记", "content": "Python 变量引用对象"}]
    provider = {"provider": "demo", "model": "demo"}
    original = answer_key("变量是什么？", docs, provider)
    assert original == answer_key(" 变量是什么？ ", docs, provider)
    assert original != answer_key("变量是什么？", [], provider)
    assert original != answer_key("变量是什么？", docs, {"provider": "compatible", "model": "other"})
    docs[0]["content"] += "。修改不会保留旧答案。"
    assert original != answer_key("变量是什么？", docs, provider)
    assert "Python" not in original


@pytest.mark.asyncio
async def test_missing_cache_is_optional():
    cache = AnswerCache()
    assert await cache.get("key") is None
    await cache.put("key", {"answer": "回答", "sources": []})
    await cache.close()


@pytest.mark.asyncio
async def test_cache_outage_does_not_interrupt_learning():
    class OfflineRedis:
        async def get(self, key):
            raise ConnectionError("offline")

        async def set(self, *args, **kwargs):
            raise ConnectionError("offline")

        async def aclose(self):
            pass

    cache = AnswerCache()
    cache.client = OfflineRedis()
    assert await cache.get("key") is None
    await cache.put("key", {"answer": "回答", "sources": []})
    await cache.close()
