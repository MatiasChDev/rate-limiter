import time

import redis
from fastapi import FastAPI, Request
from prometheus_fastapi_instrumentator import Instrumentator

from rate_limiters import TokenBucketMiddleware, TokenBucketRateLimiter

redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)

app = FastAPI()
rate_limiter = TokenBucketRateLimiter(
    redis_client, max_tokens=15, refill_rate=2
)
app.add_middleware(TokenBucketMiddleware, rate_limiter=rate_limiter)

Instrumentator(excluded_handlers=["/metrics"]).instrument(app).expose(app)


@app.get("/")
async def hello(name: str = None):
    if name:
        return {"Hello " + name + "!"}
    else:
        return {"Hello World!"}
