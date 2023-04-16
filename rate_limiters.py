from abc import ABC, abstractmethod
from datetime import datetime as dt

from fastapi import Request


class RateLimiter(ABC):
    @abstractmethod
    def receive_request(self, request: Request) -> bool:
        pass


class TokenBucket(RateLimiter):
    def __init__(self, max_tokens: int = 4, flow_rate: int = 2) -> None:
        self.max_tokens = max_tokens
        self.flow_rate = flow_rate
        self.buckets = {}

    def receive_request(self, request: Request) -> bool:
        ip = request.client.host
        current_time = dt.now()
        if ip not in self.buckets:
            self.buckets[ip] = {
                "tokens": self.max_tokens,
                "last_request": current_time,
            }
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
