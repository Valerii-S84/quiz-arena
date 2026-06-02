from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.fsm.storage.redis import RedisStorage


class LoopAwareRedisStorage(BaseStorage):
    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._storages: dict[int, RedisStorage] = {}

    def _storage(self) -> RedisStorage:
        loop_id = id(asyncio.get_running_loop())
        storage = self._storages.get(loop_id)
        if storage is None:
            storage = RedisStorage.from_url(self._redis_url)
            self._storages[loop_id] = storage
        return storage

    async def set_state(self, key: StorageKey, state: str | State | None = None) -> None:
        await self._storage().set_state(key=key, state=state)

    async def get_state(self, key: StorageKey) -> str | None:
        return await self._storage().get_state(key=key)

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        await self._storage().set_data(key=key, data=data)

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        return await self._storage().get_data(key=key)

    async def update_data(self, key: StorageKey, data: Mapping[str, Any]) -> dict[str, Any]:
        return await self._storage().update_data(key=key, data=data)

    async def close(self) -> None:
        loop_id = id(asyncio.get_running_loop())
        storage = self._storages.pop(loop_id, None)
        if storage is not None:
            await storage.close()
