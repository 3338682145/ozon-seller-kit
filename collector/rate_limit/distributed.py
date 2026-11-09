"""Distributed source-wide concurrency and token-bucket permits in Redis.

No policy may be raised by an automatic agent. Leases have finite TTL.
"""
from __future__ import annotations
import asyncio
import time
from uuid import uuid4
from collector.errors import PolicyViolation

LUA = """
local source = KEYS[1]
local active = KEYS[2]
local now = tonumber(ARGV[1]); local rate = tonumber(ARGV[2]); local burst = tonumber(ARGV[3])
local maxcon = tonumber(ARGV[4]); local ttl = tonumber(ARGV[5]); local owner = ARGV[6]
redis.call('ZREMRANGEBYSCORE', active, '-inf', now)
if redis.call('ZCARD', active) >= maxcon then return 0 end
local values = redis.call('HMGET', source, 'tokens', 't')
local tokens = tonumber(values[1]) or burst
local last = tonumber(values[2]) or now
tokens = math.min(burst, tokens + math.max(0, now-last)*rate)
if tokens < 1 then
 redis.call('HMSET', source, 'tokens', tokens, 't', now)
 redis.call('EXPIRE', source, 3600)
 return 0
end
redis.call('HMSET', source, 'tokens', tokens - 1, 't', now)
redis.call('EXPIRE', source, 3600)
redis.call('ZADD', active, now+ttl, owner)
redis.call('EXPIRE', active, math.ceil(ttl*2))
return 1
"""


class DistributedPermit:
    def __init__(self, redis_client, source_id: str, rate: float, burst: int, concurrency: int, timeout: float):
        if not (rate > 0 and burst >= 1 and concurrency >= 1 and timeout > 0):
            raise PolicyViolation("unverified/invalid rate policy")
        self.redis, self.source_id, self.rate, self.burst = redis_client, source_id, rate, burst
        self.concurrency, self.timeout = concurrency, timeout
        self.owner = str(uuid4())
        self.active_key = f"rl:active:{source_id}"

    async def __aenter__(self):
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            ok = await self.redis.eval(LUA, 2, f"rl:bucket:{self.source_id}", self.active_key, time.time(), self.rate, self.burst, self.concurrency, self.timeout + 5, self.owner)
            if ok:
                return self
            await asyncio.sleep(0.1)
        raise PolicyViolation("rate/concurrency permit deadline reached")

    async def __aexit__(self, exc_type, exc, tb):
        await self.redis.zrem(self.active_key, self.owner)
