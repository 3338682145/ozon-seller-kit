"""Redis Streams child-task broker, with priority streams and XAUTOCLAIM."""
from __future__ import annotations
from dataclasses import dataclass
import time


@dataclass(frozen=True)
class Message:
    stream: str
    message_id: str
    job_id: str


class RedisStreamBroker:
    def __init__(self, redis, stream: str = "collection:tasks", group: str = "collection-workers", dlq: str = "collection:dlq"):
        self.redis, self.stream, self.group, self.dlq = redis, stream, group, dlq
        self.streams = [f"{stream}:high", f"{stream}:normal", f"{stream}:low"]

    def choose(self, priority: int) -> str:
        return self.streams[0 if priority > 0 else 2 if priority < 0 else 1]

    async def setup(self):
        for s in self.streams:
            try:
                await self.redis.xgroup_create(s, self.group, id="0", mkstream=True)
            except Exception as e:
                if "BUSYGROUP" not in str(e):
                    raise

    async def publish(self, job_id: str, priority: int = 0):
        # Never trim a stream before every consumer-group pending entry is ACKed.
        return await self.redis.xadd(self.choose(priority), {"job_id": job_id})

    async def backlog(self):
        return sum([await self.redis.xlen(s) for s in self.streams])

    async def receive(self, consumer: str, *, block_ms: int = 1000) -> Message | None:
        for s in self.streams:
            records = await self.redis.xreadgroup(self.group, consumer, streams={s: ">"}, count=1, block=min(block_ms, 100))
            if records:
                stream, messages = records[0]
                mid, fields = messages[0]
                return Message(stream=stream.decode() if isinstance(stream, bytes) else stream,
                               message_id=mid.decode() if isinstance(mid, bytes) else mid,
                               job_id=(fields.get(b"job_id") or fields.get("job_id")).decode() if isinstance(fields.get(b"job_id") or fields.get("job_id"), bytes) else fields.get("job_id"))
        return None

    async def recover(self, consumer: str, *, idle_ms: int = 60000) -> Message | None:
        for s in self.streams:
            result = await self.redis.xautoclaim(s, self.group, consumer, min_idle_time=idle_ms, start_id="0-0", count=1)
            rows = result[1]
            if rows:
                mid, fields = rows[0]
                def dec(x): return x.decode() if isinstance(x, bytes) else x
                return Message(s, dec(mid), dec(fields.get("job_id") or fields.get(b"job_id")))
        return None

    async def ack(self, msg: Message):
        await self.redis.xack(msg.stream, self.group, msg.message_id)
        await self.redis.xdel(msg.stream, msg.message_id)  # prevents permanent backlog growth

    async def dead_letter(self, job_id: str, code: str):
        await self.redis.xadd(self.dlq, {"job_id": job_id, "error_code": code[:64]})


class MemoryBroker:
    """Deterministic mock of XREADGROUP + pending entry list for crash tests."""
    def __init__(self):
        self.next_id = 0
        self.ready: list[Message] = []
        self.pending: dict[str, Message] = {}
        self.dlq: list[dict] = []

    async def setup(self):
        pass

    async def publish(self, job_id: str, priority: int = 0):
        self.next_id += 1
        msg = Message("memory", str(self.next_id), job_id)
        self.ready.append(msg)
        self.ready.sort(key=lambda x: 0 if priority > 0 else 1 if priority == 0 else 2)
        return msg.message_id

    async def backlog(self):
        return len(self.ready) + len(self.pending)

    async def receive(self, consumer: str, *, block_ms: int = 0):
        if not self.ready:
            return None
        msg = self.ready.pop(0)
        self.pending[msg.message_id] = msg
        return msg

    async def recover(self, consumer: str, *, idle_ms: int = 0):
        return next(iter(self.pending.values()), None)

    async def ack(self, msg: Message):
        self.pending.pop(msg.message_id, None)

    async def dead_letter(self, job_id: str, code: str):
        self.dlq.append({"job_id": job_id, "code": code})
