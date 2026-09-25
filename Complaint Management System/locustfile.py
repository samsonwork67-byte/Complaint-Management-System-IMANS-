from locust import HttpUser, task, between


class AuditUser(HttpUser):
    host = "http://127.0.0.1:5000"
    wait_time = between(1, 3)

    def on_start(self):
        login_resp = self.client.post(
            "/login",
            data={"username": "admin", "password": "1234"},
            allow_redirects=True
        )
        # Validate session by calling /api/me (Flask login redirects with 302)
        me_resp = self.client.get("/api/me")
        try:
            data = me_resp.json()
            self.is_admin = bool(data.get("is_admin"))
            if not self.is_admin:
                print("Login did not establish admin session:", me_resp.text[:500])
            else:
                print("Logged in as admin (session established)")
        except Exception:
            self.is_admin = False
            print("Failed to parse /api/me response:", me_resp.status_code, me_resp.text[:500])

    @task
    def flow(self):
        self.client.get("/api/me")

        self.client.get("/api/audit-log/feed?limit=30")

        self.client.post(
            "/api/audit-log",
            json={
                "action_type": "VIEW",
                "target": "locust-test",
                "details": {"source": "locust"}
            }
        )