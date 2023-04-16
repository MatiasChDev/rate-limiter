import time

from fastapi import FastAPI, Request
from prometheus_fastapi_instrumentator import Instrumentator

from rate_limiters import TokenBucketMiddleware, TokenBucketRateLimiter

app = FastAPI()
rate_limiter = TokenBucketRateLimiter(flow_rate=2, max_tokens=15)
app.add_middleware(TokenBucketMiddleware, rate_limiter=rate_limiter)

Instrumentator(excluded_handlers=["/metrics"]).instrument(app).expose(app)


@app.get("/")
async def hello(name: str = None):
    if name:
        return {"Hello " + name + "!"}
    else:
        return {"Hello World!"}


# @app.middleware("http")
# async def test_middleware(request: Request, call_next):
#     if request.url.path == "/metrics":
#         response = await call_next(request)
#         return response

#     if rate_limiter.receive_request(request):
#         response = await call_next(request)
#         return response
#     else:
#         print("Over limit")
