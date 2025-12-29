from langgraph.checkpoint.redis import AsyncRedisSaver
from redis.asyncio import Redis
from contextlib import asynccontextmanager

class PerUserRedisSaver(AsyncRedisSaver):
    def __init__(self, redis: Redis, ttl_resolver):
        super().__init__(redis=redis)
        self.ttl_resolver = ttl_resolver

    @classmethod
    @asynccontextmanager
    async def from_conn_string(cls, conn_string: str, *, ttl_resolver):
        redis = Redis.from_url(conn_string)
        try:
            yield cls(redis=redis, ttl_resolver=ttl_resolver)
        finally:
            await redis.close()

    def _key(self, config):
        c = config["configurable"]
        return f"lg:{c['user_id']}:{c['thread_id']}"

    async def aset_tuple(self, config, checkpoint):
        ttl = self.ttl_resolver(config)
        await self.redis.set(
            self._key(config),
            self.serializer.dumps(checkpoint),
            ex=ttl,
        )

    async def aget_tuple(self, config):
        raw = await self.redis.get(self._key(config))
        return None if raw is None else self.serializer.loads(raw)
