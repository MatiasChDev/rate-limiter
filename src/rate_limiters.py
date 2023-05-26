import asyncio
import pickle
import time
from abc import ABC, abstractmethod
from typing import Callable, Dict

from fastapi import Request
from redis import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# TODO Add comments
# TODO: Use pipelines
# TODO: Implement leakingbucket with redis and stateless


class RateLimiter(ABC):
    @abstractmethod
    def receive_request(self, request: Request) -> bool:
        pass


class SlidingWindowCounterRateLimiter(RateLimiter):
    def __init__(self, redis_client: Redis, max_requests: int = 4, interval: float = 10) -> None:
        self.redis_client = redis_client
        self.max_requests = max_requests
        self.interval = interval

    async def receive_request(self, request: Request) -> bool:
        now = time.time()
        current_interval = int(now / self.interval)
        previous_interval = current_interval - 1
        r = self.redis_client
        ip = request.client.host
        r.set(f"{ip}_{current_interval}", 0, nx=True, ex=self.interval * 2)
        current_interval_requests = int(r.get(f"{ip}_{current_interval}"))
        previous_interval_requests = int(r.get(f"{ip}_{previous_interval}") or 0)
        overlap = 1 - (now / self.interval) % 1
        rolling_window_requests = current_interval_requests + int(
            overlap * previous_interval_requests
        )
        if rolling_window_requests >= self.max_requests:
            return False
        r.incr(f"{ip}_{current_interval}")
        return True


class SlidingWindowCounterMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Callable, rate_limiter: SlidingWindowCounterRateLimiter) -> None:
        super().__init__(app)
        self.rate_limiter = rate_limiter

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)
        if await self.rate_limiter.receive_request(request):
            return await call_next(request)
        else:
            return JSONResponse(content={"message": "Over limit"}, status_code=429)


class SlidingWindowRateLimiter(RateLimiter):
    def __init__(self, redis_client: Redis, max_requests: int = 4, interval: float = 10) -> None:
        self.redis_client = redis_client
        self.max_requests = max_requests
        self.interval = interval

    async def receive_request(self, request: Request) -> bool:
        now = time.time()
        self.redis_client.zremrangebyscore(request.client.host, "-inf", now - self.interval)
        if (
            len(self.redis_client.zrangebyscore(request.client.host, now - self.interval, now))
            >= self.max_requests
        ):
            return False
        self.redis_client.zadd(request.client.host, {now: now})
        return True


class SlidingWindowMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Callable, rate_limiter: SlidingWindowRateLimiter) -> None:
        super().__init__(app)
        self.rate_limiter = rate_limiter

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)
        if await self.rate_limiter.receive_request(request):
            return await call_next(request)
        else:
            return JSONResponse(content={"message": "Over limit"}, status_code=429)


class FixedWindowRateLimiter(RateLimiter):
    def __init__(self, redis_client: Redis, max_requests: int = 4, interval: float = 10) -> None:
        self.redis_client = redis_client
        self.max_requests = max_requests
        self.interval = interval

    async def receive_request(self, request: Request) -> bool:
        # TODO: Switch to pipeline
        self.redis_client.set(request.client.host, self.max_requests, nx=True, ex=self.interval)
        self.redis_client.decr(request.client.host)
        count = int(self.redis_client.get(request.client.host))
        return count >= 0


class FixedWindowMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Callable, rate_limiter: FixedWindowRateLimiter) -> None:
        super().__init__(app)
        self.rate_limiter = rate_limiter

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)
        if await self.rate_limiter.receive_request(request):
            return await call_next(request)
        else:
            return JSONResponse(content={"message": "Over limit"}, status_code=429)


class LeakingBucketRateLimiterAsyncio(RateLimiter):
    # TODO: Switch to redis
    processing_queue = {}

    def __init__(self, max_size: int = 4, processing_rate: float = 1) -> None:
        self.max_size = max_size
        self.processing_rate = processing_rate

    async def receive_request(self, data: Dict) -> bool:
        ip = data["request"].client.host
        if ip not in self.processing_queue:
            self.processing_queue[ip] = asyncio.Queue(maxsize=self.max_size)
        try:
            self.processing_queue[ip].put_nowait(data)
            return True
        except asyncio.QueueFull:
            return False

    async def process_queue(self):
        while True:
            if len(self.processing_queue.keys()) > 0:
                for ip in self.processing_queue.keys():
                    if not self.processing_queue[ip].empty():
                        data = self.processing_queue[ip].get_nowait()
                        result = await data["call_next"](data["request"])
                        data["event"].set_result(result)
                for k, v in list(self.processing_queue.items()):
                    if v.empty():
                        del self.processing_queue[k]
            await asyncio.sleep(1 / self.processing_rate)


class LeakingBucketMiddlewareAsyncio(BaseHTTPMiddleware):
    def __init__(self, app: Callable, rate_limiter: LeakingBucketRateLimiterAsyncio) -> None:
        super().__init__(app)
        self.rate_limiter = rate_limiter

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)
        event = asyncio.get_event_loop().create_future()
        if await self.rate_limiter.receive_request(
            {"request": request, "event": event, "call_next": call_next}
        ):
            return await event
        else:
            return JSONResponse(content={"message": "Over limit"}, status_code=429)


class TokenBucketRateLimiter(RateLimiter):
    def __init__(self, redis_client, max_tokens: int = 4, refill_rate: float = 2) -> None:
        self.redis_client = redis_client
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate

    async def receive_request(self, request: Request) -> bool:
        ip = request.client.host
        current_time = time.time()

        # TODO: Change to use pipeline (for faster performance)
        # TODO: Use the pipeline WATCH command to make sure another process didn't change tokens
        tokens = self.redis_client.hget(ip, "tokens")
        last_update = self.redis_client.hget(ip, "last_update")

        if tokens is None:
            tokens = self.max_tokens
        else:
            tokens = float(tokens)
            elapsed_time = current_time - float(last_update)
            refill_tokens = elapsed_time * self.refill_rate
            tokens = min(self.max_tokens, tokens + refill_tokens)
        last_update = current_time
        if tokens >= 0:
            self.redis_client.hset(ip, mapping={"tokens": tokens - 1, "last_update": last_update})
            return True
        else:
            return False


class TokenBucketMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Callable, rate_limiter: TokenBucketRateLimiter) -> None:
        super().__init__(app)
        self.rate_limiter = rate_limiter

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)
        if await self.rate_limiter.receive_request(request):
            return await call_next(request)
        else:
            return JSONResponse(content={"message": "Over limit"}, status_code=429)
