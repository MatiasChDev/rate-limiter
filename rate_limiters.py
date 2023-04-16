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
    def __init__(self, max_tokens: int = 4, flow_rate: int = 2) -> None:
        self.max_tokens = max_tokens
        self.flow_rate = flow_rate
        self.buckets = {}

    def receive_request(self, request: Request) -> bool:
        ip = request.client.host
        current_time = dt.now()
        if ip not in self.buckets:
            self.buckets[ip] = {
                "tokens": self.max_tokens - 1,
                "last_request": current_time,
            }
            return True
        current_bucket = self.buckets[ip]
        time_elapsed = (
            current_time - current_bucket["last_request"]
        ).total_seconds()
        current_bucket["last_request"] = current_time
        current_bucket["tokens"] = min(
            self.max_tokens,
            current_bucket["tokens"] + time_elapsed * self.flow_rate,
        )
        if current_bucket["tokens"] >= 1:
            current_bucket["tokens"] -= 1
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
        if self.rate_limiter.receive_request(request):
            response = await call_next(request)
            return response
        else:
            print("Over limit")
