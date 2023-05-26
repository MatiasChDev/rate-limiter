import os

import uvicorn
from prometheus_fastapi_instrumentator import Instrumentator

from src.api import create_app

if __name__ == "__main__":
    rate_limiter_type = os.environ["RATE_LIMITER"]
    args = os.environ["RATE_LIMITER_ARGS"]
    split_args = [float(arg) for arg in args.split()]
    app = create_app(rate_limiter_type, *split_args)

    Instrumentator(excluded_handlers=["/metrics"]).instrument(app).expose(app)

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
