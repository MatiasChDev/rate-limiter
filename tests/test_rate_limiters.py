import sys
import time

from fastapi.testclient import TestClient

from src.api import app, redis_client

client = TestClient(app)


def test_sliding_window_counter():
    for _ in range(5):
        response = client.get("/")
        print(response)
    redis_client.flushall()
