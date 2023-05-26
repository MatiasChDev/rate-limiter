import asyncio
import inspect
import os

import redis
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from src import rate_limiters

# TODO: Switch to aioredis

rate_limiters_list = {
    "TokenBucket": (
        rate_limiters.TokenBucketRateLimiter,
        rate_limiters.TokenBucketMiddleware,
    ),
    "LeakingBucket": (
        rate_limiters.LeakingBucketRateLimiter,
        rate_limiters.LeakingBucketMiddleware,
    ),
    "FixedWindow": (
        rate_limiters.FixedWindowRateLimiter,
        rate_limiters.FixedWindowMiddleware,
    ),
    "SlidingWindow": (
        rate_limiters.SlidingWindowRateLimiter,
        rate_limiters.SlidingWindowMiddleware,
    ),
    "SlidingWindowCounter": (
        rate_limiters.SlidingWindowCounterRateLimiter,
        rate_limiters.SlidingWindowCounterMiddleware,
    ),
}


def create_app():
    app = FastAPI()
    redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)
    redis_client.flushall()
    rate_limiter_type = os.environ["RATE_LIMITER"]
    rate_limiter_func = rate_limiters_list[rate_limiter_type][0]
    args = os.environ["RATE_LIMITER_ARGS"]
    split_args = [float(arg) for arg in args.split()]
    rate_limiter = rate_limiter_func(redis_client, *split_args)
    middleware = rate_limiters_list[rate_limiter_type][1]
    app.add_middleware(middleware, rate_limiter=rate_limiter)

    @app.on_event("startup")
    async def startup():
        if isinstance(
            rate_limiter,
            (rate_limiters.LeakingBucketRateLimiterAsyncio),
        ):
            asyncio.create_task(rate_limiter.process_queue())

    @app.get("/")
    async def hello(name: str = None):
        return {f"Hello {name}!"} if name else {"Hello World!"}

    return app


app = create_app()

Instrumentator(excluded_handlers=["/metrics"]).instrument(app).expose(app)
