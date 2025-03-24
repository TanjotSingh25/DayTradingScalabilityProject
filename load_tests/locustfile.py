from locust import HttpUser, task, between

class AuthUser(HttpUser):
    wait_time = between(1, 2)  # Wait time between tasks

    @task
    def login(self):
        self.client.post("/authentication/login", json={"user_name": "testuser", "password": "password"})

    @task
    def register(self):
        self.client.post("/authentication/register", json={"user_name": "newuser", "password": "password", "name": "Test User"})
