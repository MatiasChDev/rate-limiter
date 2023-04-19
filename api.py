import asyncio
import time

import redis
from fastapi import FastAPI, Request
from prometheus_fastapi_instrumentator import Instrumentator

from rate_limiters import (
    LeakingBucketMiddleware,
    LeakingBucketRateLimiter,
    TokenBucketMiddleware,
    TokenBucketRateLimiter,
)

redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)

app = FastAPI()
rate_limiter = LeakingBucketRateLimiter(max_size=4, processing_rate=1)
middleware = LeakingBucketMiddleware
app.add_middleware(middleware, rate_limiter=rate_limiter)

Instrumentator(excluded_handlers=["/metrics"]).instrument(app).expose(app)


@app.on_event("startup")
async def startup():
    if isinstance(rate_limiter, (LeakingBucketRateLimiter)):
        asyncio.create_task(rate_limiter.process_queue())


@app.get("/")
async def hello(name: str = None):
    if name:
        return {"Hello " + name + "!"}
    else:
        return {"Hello World!"}
