"""认证链路测试。"""
from httpx import AsyncClient


class TestAuthFlow:

    async def test_login_admin(self, client: AsyncClient, auth_headers: dict):
        assert auth_headers["Authorization"].startswith("Bearer ")

    async def test_login_wrong_password(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post("/api/auth/token", data={
            "username": "testadmin",
            "password": "wrong",
        })
        assert resp.status_code == 401

    async def test_read_current_user(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/auth/users/me", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["username"] == "testadmin"

    async def test_unauthorized_access(self, client: AsyncClient):
        resp = await client.get("/api/auth/users/me")
        assert resp.status_code == 401

    async def test_admin_endpoint_for_normal_user(self, client: AsyncClient, user_headers: dict):
        resp = await client.get("/api/admin/users", headers=user_headers)
        assert resp.status_code == 403

    async def test_register_missing_code(self, client: AsyncClient):
        """缺少验证码的注册应被拒绝。"""
        resp = await client.post("/api/auth/users", json={
            "username": "newuser",
            "email": "new@example.com",
            "password": "Password123!",
        })
        assert resp.status_code == 422

    async def test_health_endpoint(self, client: AsyncClient):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
