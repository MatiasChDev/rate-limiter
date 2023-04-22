from locust import HttpUser, between, task


class APIUser(HttpUser):
    wait_time = between(0.1, 0.1)

    @task
    def get_rate_limited_endpoint(self):
        self.client.get("/")
