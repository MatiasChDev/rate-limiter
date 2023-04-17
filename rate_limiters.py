import time
from abc import ABC, abstractmethod
from datetime import datetime as dt
from typing import Callable, Dict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimiter(ABC):
    @abstractmethod
    def receive_request(self, request: Request) -> bool:
        pass


class LeakingBucket(RateLimiter):
    def __init__(self, max_size: int = 4) -> None:
        self.buckets = {}

    def receive_request(self, request: Request) -> bool:
        ip = request.client.host
        if ip not in self.buckets:
            self.buckets[ip] = []
        current_bucket = self.buckets[ip]
        if len(current_bucket) > self.max_size:
            return False


class TokenBucketRateLimiter(RateLimiter):
    def __init__(
        self, redis_client, max_tokens: int = 4, refill_rate: float = 2
    ) -> None:
        self.redis_client = redis_client
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate
        # self.buckets = {}

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
