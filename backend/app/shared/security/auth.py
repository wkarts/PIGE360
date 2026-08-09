from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Callable

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, Header, Request

from app.bootstrap.config import Settings
from app.shared.database.store import SQLiteStore
from app.shared.domain.ids import iso_now, uuid7
from app.shared.presentation.errors import DomainError

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise DomainError("WEAK_PASSWORD", "A senha deve possuir ao menos 10 caracteres.", 422)
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: str
    tenant_id: str | None
    person_id: str | None
    email: str
    roles: tuple[str, ...]
    plane: str

    def has_any_role(self, required: set[str]) -> bool:
        return bool(required.intersection(self.roles))


class AuthService:
    def __init__(self, store: SQLiteStore, settings: Settings, *, tenant_id: str | None, plane: str):
        self.store = store
        self.settings = settings
        self.tenant_id = tenant_id
        self.plane = plane

    def create_user(self, email: str, password: str, roles: list[str], person_id: str | None = None) -> dict[str, Any]:
        now = iso_now(); user_id = uuid7()
        with self.store.transaction() as conn:
            existing = conn.execute("SELECT id FROM users WHERE tenant_id IS ? AND email=?", (self.tenant_id, email.lower())).fetchone()
            if existing:
                raise DomainError("EMAIL_ALREADY_EXISTS", "Já existe usuário com este e-mail.", 409)
            conn.execute(
                "INSERT INTO users(id,tenant_id,person_id,email,password_hash,roles_json,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (user_id, self.tenant_id, person_id, email.lower(), hash_password(password), json.dumps(sorted(set(roles))), 1, now, now),
            )
        return {"id": user_id, "person_id": person_id, "email": email.lower(), "roles": sorted(set(roles)), "tenant_id": self.tenant_id}

    def login(self, email: str, password: str) -> dict[str, Any]:
        row = self.store.fetch_one("SELECT * FROM users WHERE tenant_id IS ? AND email=? AND active=1", (self.tenant_id, email.lower()))
        if not row or not verify_password(row["password_hash"], password):
            raise DomainError("INVALID_CREDENTIALS", "E-mail ou senha inválidos.", 401, "Não autenticado")
        roles = tuple(json.loads(row["roles_json"]))
        return self._tokens(row["id"], row["email"], roles)

    def _tokens(self, user_id: str, email: str, roles: tuple[str, ...]) -> dict[str, Any]:
        now = datetime.now(UTC)
        access_exp = now + timedelta(minutes=self.settings.access_token_minutes)
        access_jti = uuid7()
        claims = {
            "sub": user_id, "email": email, "roles": list(roles), "tid": self.tenant_id,
            "plane": self.plane, "iss": self.settings.jwt_issuer, "aud": f"pige360:{self.plane}",
            "iat": int(now.timestamp()), "nbf": int(now.timestamp()), "exp": int(access_exp.timestamp()), "jti": access_jti,
        }
        access = jwt.encode(claims, self.settings.jwt_secret, algorithm="HS256")
        refresh = secrets.token_urlsafe(48)
        refresh_hash = hashlib.sha256(refresh.encode()).hexdigest()
        refresh_jti = uuid7(); refresh_exp = now + timedelta(days=self.settings.refresh_token_days)
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO refresh_tokens(jti,user_id,tenant_id,token_hash,expires_at,created_at) VALUES(?,?,?,?,?,?)",
                (refresh_jti, user_id, self.tenant_id, refresh_hash, refresh_exp.isoformat(), iso_now()),
            )
        return {
            "token_type": "Bearer", "access_token": access, "expires_in": self.settings.access_token_minutes * 60,
            "refresh_token": f"{refresh_jti}.{refresh}", "refresh_expires_at": refresh_exp.isoformat(),
        }

    def rotate_refresh(self, token: str) -> dict[str, Any]:
        try:
            jti, secret = token.split(".", 1)
        except ValueError as exc:
            raise DomainError("INVALID_REFRESH_TOKEN", "Refresh token inválido.", 401) from exc
        digest = hashlib.sha256(secret.encode()).hexdigest()
        row = self.store.fetch_one("SELECT * FROM refresh_tokens WHERE jti=?", (jti,))
        if not row or not secrets.compare_digest(row["token_hash"], digest) or row["revoked_at"]:
            raise DomainError("INVALID_REFRESH_TOKEN", "Refresh token inválido ou revogado.", 401)
        if datetime.fromisoformat(row["expires_at"]).astimezone(UTC) <= datetime.now(UTC):
            raise DomainError("EXPIRED_REFRESH_TOKEN", "Refresh token expirado.", 401)
        user = self.store.fetch_one("SELECT * FROM users WHERE id=? AND active=1", (row["user_id"],))
        if not user:
            raise DomainError("USER_DISABLED", "Usuário indisponível.", 401)
        result = self._tokens(user["id"], user["email"], tuple(json.loads(user["roles_json"])))
        new_jti = result["refresh_token"].split(".", 1)[0]
        with self.store.transaction() as conn:
            conn.execute("UPDATE refresh_tokens SET revoked_at=?, replaced_by=? WHERE jti=?", (iso_now(), new_jti, jti))
        return result


def decode_access(token: str, settings: Settings, expected_plane: str, expected_tenant_id: str | None) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            token, settings.jwt_secret, algorithms=["HS256"], issuer=settings.jwt_issuer,
            audience=f"pige360:{expected_plane}", options={"require": ["exp", "iat", "sub", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise DomainError("TOKEN_EXPIRED", "Token de acesso expirado.", 401, "Não autenticado") from exc
    except jwt.PyJWTError as exc:
        raise DomainError("INVALID_TOKEN", "Token de acesso inválido.", 401, "Não autenticado") from exc
    if claims.get("plane") != expected_plane or claims.get("tid") != expected_tenant_id:
        raise DomainError("TOKEN_SCOPE_MISMATCH", "O token não pertence a este domínio.", 403, "Acesso negado")
    return claims


def current_user(request: Request, authorization: Annotated[str | None, Header()] = None) -> CurrentUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise DomainError("AUTH_REQUIRED", "Informe um token Bearer.", 401, "Não autenticado")
    token = authorization.removeprefix("Bearer ").strip()
    resolution = request.state.host_resolution
    claims = decode_access(token, request.app.state.settings, resolution.plane, resolution.tenant_id)
    row = request.state.store.fetch_one("SELECT id,person_id,email,roles_json,active FROM users WHERE id=?", (claims["sub"],))
    if not row or not row["active"]:
        raise DomainError("USER_DISABLED", "Usuário indisponível.", 401)
    return CurrentUser(row["id"], resolution.tenant_id, row.get("person_id"), row["email"], tuple(json.loads(row["roles_json"])), resolution.plane)


def require_roles(*roles: str) -> Callable[[CurrentUser], CurrentUser]:
    required = set(roles)
    def dependency(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if not user.has_any_role(required):
            raise DomainError("PERMISSION_DENIED", "Permissão insuficiente para esta operação.", 403, "Acesso negado")
        return user
    return dependency
