from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from app.bootstrap.config import Settings
import app.shared.security.auth as auth_module
from app.main import create_app

PLATFORM_HOST = "api.platform.local"
ALPHA_HOST = "admin.alpha.school.local"
BETA_HOST = "admin.beta.school.local"
PASSWORD = "Senha-Forte-Local-2026!"


@dataclass
class LocalEnvironment:
    client: TestClient
    root: Path
    platform_token: str
    alpha_token: str
    beta_token: str
    alpha_tenant: dict[str, Any]
    beta_tenant: dict[str, Any]

    @staticmethod
    def headers(host: str, token: str | None = None, **extra: str) -> dict[str, str]:
        result = {"host": host}
        if token:
            result["Authorization"] = f"Bearer {token}"
        result.update(extra)
        return result

    def alpha_headers(self, **extra: str) -> dict[str, str]:
        return self.headers(ALPHA_HOST, self.alpha_token, **extra)

    def beta_headers(self, **extra: str) -> dict[str, str]:
        return self.headers(BETA_HOST, self.beta_token, **extra)

    def platform_headers(self, **extra: str) -> dict[str, str]:
        return self.headers(PLATFORM_HOST, self.platform_token, **extra)

    def create_alpha_user(self, email: str, roles: list[str], password: str = PASSWORD, person_id: str | None = None) -> tuple[dict[str, Any], str]:
        response = self.client.post(
            "/api/v1/auth/users",
            headers=self.alpha_headers(),
            json={"email": email, "password": password, "roles": roles, "person_id": person_id},
        )
        assert response.status_code == 201, response.text
        user = response.json()
        login = self.client.post(
            "/api/v1/auth/login",
            headers=self.headers(ALPHA_HOST),
            json={"email": email, "password": password},
        )
        assert login.status_code == 200, login.text
        return user, login.json()["access_token"]


@pytest.fixture()
def local_env(tmp_path: Path) -> LocalEnvironment:
    # Mantém o algoritmo Argon2 e reduz apenas o custo da suíte local isolada.
    auth_module._hasher = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)
    settings = Settings().testing(tmp_path / "runtime")
    app = create_app(settings)
    with TestClient(app) as client:
        bootstrap = client.post(
            "/api/v1/platform/bootstrap",
            headers={"host": PLATFORM_HOST, "X-Bootstrap-Token": settings.bootstrap_token},
            json={"email": "root@platform.example.com", "password": PASSWORD},
        )
        assert bootstrap.status_code == 200, bootstrap.text
        login = client.post(
            "/api/v1/auth/login",
            headers={"host": PLATFORM_HOST},
            json={"email": "root@platform.example.com", "password": PASSWORD},
        )
        assert login.status_code == 200, login.text
        platform_token = login.json()["access_token"]

        def provision(code: str, hostname: str, owner: str) -> dict[str, Any]:
            response = client.post(
                "/api/v1/platform/tenants",
                headers={"host": PLATFORM_HOST, "Authorization": f"Bearer {platform_token}"},
                json={
                    "code": code,
                    "legal_name": f"Instituição {code.title()} Ltda.",
                    "trade_name": f"Colégio {code.title()}",
                    "hostname": hostname,
                    "owner_email": owner,
                    "owner_password": PASSWORD,
                },
            )
            assert response.status_code == 201, response.text
            return response.json()

        alpha = provision("alpha-school", ALPHA_HOST, "owner@alpha.example.com")
        beta = provision("beta-school", BETA_HOST, "owner@beta.example.com")

        def tenant_login(host: str, email: str) -> str:
            response = client.post(
                "/api/v1/auth/login",
                headers={"host": host},
                json={"email": email, "password": PASSWORD},
            )
            assert response.status_code == 200, response.text
            return response.json()["access_token"]

        env = LocalEnvironment(
            client=client,
            root=settings.data_root,
            platform_token=platform_token,
            alpha_token=tenant_login(ALPHA_HOST, "owner@alpha.example.com"),
            beta_token=tenant_login(BETA_HOST, "owner@beta.example.com"),
            alpha_tenant=alpha,
            beta_tenant=beta,
        )
        yield env
