import sys
import time

from fastapi.testclient import TestClient

from src.api import create_app, redis_client


def test_sliding_window_counter():
    app = create_app("SlidingWindow", 4, 5)
    client = TestClient(app)
    redis_client.flushall()

    for _ in range(4):
        response = client.get("/")
        assert response.status_code == 200
    for _ in range(1):
        response = client.get("/")
        assert response.status_code == 429
