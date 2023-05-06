import asyncio
import time
from abc import ABC, abstractmethod
from typing import Callable, Dict

from fastapi import Request
from redis import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimiter(ABC):
    @abstractmethod
    def receive_request(self, request: Request) -> bool:
        pass


class FixedWindowRateLimiter(RateLimiter):
    def __init__(
        self, redis_client: Redis, max_requests: int = 4, interval: float = 10
    ) -> None:
        self.redis_client = redis_client
        self.max_requests = max_requests
        self.interval = interval

    async def receive_request(self, request: Request) -> bool:
        self.redis_client.set(
            request.client.host, self.max_requests, nx=True, ex=self.interval
        )
        self.redis_client.decr(request.client.host)
        count = int(self.redis_client.get(request.client.host))
        print(count)
        if count > 0:
            return True
        else:
            return False


class FixedWindowMiddleware(BaseHTTPMiddleware):
    def __init__(
        self, app: Callable, rate_limiter: FixedWindowRateLimiter
    ) -> None:
        super().__init__(app)
        self.rate_limiter = rate_limiter

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/metrics":
            response = await call_next(request)
            return response
        if await self.rate_limiter.receive_request(request):
            response = await call_next(request)
            return response
        else:
            print("Over limit")
            return JSONResponse(
                content={"message": "Over limit"}, status_code=429
            )


class LeakingBucketRateLimiterAsyncio(RateLimiter):
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
    def __init__(
        self, app: Callable, rate_limiter: LeakingBucketRateLimiterAsyncio
    ) -> None:
        super().__init__(app)
        self.rate_limiter = rate_limiter

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/metrics":
            response = await call_next(request)
            return response
        event = asyncio.get_event_loop().create_future()
        if await self.rate_limiter.receive_request(
            {"request": request, "event": event, "call_next": call_next}
        ):
            response = await event
            return response
        else:
            print("Over limit")
            return JSONResponse(
                content={"message": "Over limit"}, status_code=429
            )


class TokenBucketRateLimiter(RateLimiter):
    def __init__(
        self, redis_client, max_tokens: int = 4, refill_rate: float = 2
    ) -> None:
        self.redis_client = redis_client
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate

    async def receive_request(self, request: Request) -> bool:
        ip = request.client.host
        current_time = time.time()

        tokens = self.redis_client.hget(ip, "tokens")
        last_update = self.redis_client.hget(ip, "last_update")

        if tokens is None:
            tokens = self.max_tokens
            last_update = current_time
        else:
            tokens = float(tokens)
            last_update = float(last_update)
            elapsed_time = current_time - last_update
            refill_tokens = elapsed_time * self.refill_rate
            tokens = min(self.max_tokens, tokens + refill_tokens)
            last_update = current_time

        if tokens >= 0:
            self.redis_client.hset(
                ip, mapping={"tokens": tokens - 1, "last_update": last_update}
            )
            return True
        else:
            return False


class TokenBucketMiddleware(BaseHTTPMiddleware):
    def __init__(
        self, app: Callable, rate_limiter: TokenBucketRateLimiter
    ) -> None:
        super().__init__(app)
        self.rate_limiter = rate_limiter

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/metrics":
            response = await call_next(request)
            return response
        if await self.rate_limiter.receive_request(request):
            response = await call_next(request)
            return response
        else:
            print("Over limit")
            return JSONResponse(
                content={"message": "Over limit"}, status_code=429
            )
