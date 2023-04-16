import time

from fastapi import FastAPI, Request
from prometheus_fastapi_instrumentator import Instrumentator

from rate_limiters import TokenBucket

app = FastAPI()
Instrumentator(excluded_handlers=["/metrics"]).instrument(app).expose(app)
rate_limiter = TokenBucket(flow_rate=2, max_tokens=50)


@app.get("/")
async def hello(name: str = None):
    if name:
        return {"Hello " + name + "!"}
    else:
        return {"Hello World!"}


@app.middleware("http")
async def test_middleware(request: Request, call_next):
    if request.url.path == "/metrics":
        response = await call_next(request)
        return response

    if rate_limiter.receive_request(request):
        response = await call_next(request)
        return response
    else:
        print("Over limit")
