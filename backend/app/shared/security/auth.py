from __future__ import annotations

import hashlib
import hmac
import json
import math
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
    session_id: str | None = None

    def has_any_role(self, required: set[str]) -> bool:
        return bool(required.intersection(self.roles))


class AuthService:
    def __init__(self, store: SQLiteStore, settings: Settings, *, tenant_id: str | None, plane: str):
        self.store = store
        self.settings = settings
        self.tenant_id = tenant_id
        self.plane = plane

    def create_user(
        self,
        email: str,
        password: str,
        roles: list[str],
        person_id: str | None = None,
        *,
        max_active_users: int | None = None,
    ) -> dict[str, Any]:
        now = iso_now(); user_id = uuid7()
        with self.store.transaction() as conn:
            if max_active_users is not None:
                if max_active_users < 1:
                    raise DomainError("TENANT_QUOTAS_INVALID", "A quota de usuários do tenant é inválida.", 503)
                self.store.transaction_lock(conn, f"tenant-active-user-quota:{self.tenant_id}")
            existing = conn.execute("SELECT id FROM users WHERE tenant_id IS ? AND email=?", (self.tenant_id, email.lower())).fetchone()
            if existing:
                raise DomainError("EMAIL_ALREADY_EXISTS", "Já existe usuário com este e-mail.", 409)
            if max_active_users is not None:
                active_users = conn.execute(
                    "SELECT COUNT(*) AS n FROM users WHERE tenant_id IS ? AND active=1",
                    (self.tenant_id,),
                ).fetchone()
                if int(active_users["n"] if active_users else 0) >= max_active_users:
                    raise DomainError(
                        "TENANT_QUOTA_EXCEEDED",
                        f"A quota de usuários ativos ({max_active_users}) foi atingida.",
                        409,
                    )
            conn.execute(
                "INSERT INTO users(id,tenant_id,person_id,email,password_hash,roles_json,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (user_id, self.tenant_id, person_id, email.lower(), hash_password(password), json.dumps(sorted(set(roles))), 1, now, now),
            )
        return {"id": user_id, "person_id": person_id, "email": email.lower(), "roles": sorted(set(roles)), "tenant_id": self.tenant_id}

    def login(self, email: str, password: str) -> dict[str, Any]:
        normalized_email = email.strip().lower()
        identifier_hash = self._login_identifier_hash(normalized_email)
        now = datetime.now(UTC)
        self._enforce_login_lock(identifier_hash, now)
        row = self.store.fetch_one(
            "SELECT * FROM users WHERE tenant_id IS ? AND email=? AND active=1",
            (self.tenant_id, normalized_email),
        )
        if not row or not verify_password(row["password_hash"], password):
            self._record_failed_login(identifier_hash, now)
            raise DomainError("INVALID_CREDENTIALS", "E-mail ou senha inválidos.", 401, "Não autenticado")
        self.store.execute("DELETE FROM auth_login_attempts WHERE identifier_hash=?", (identifier_hash,))
        roles = tuple(json.loads(row["roles_json"]))
        return self._tokens(row["id"], row["email"], roles)

    def _login_identifier_hash(self, normalized_email: str) -> str:
        scope = self.tenant_id or "platform"
        value = f"pige360/login/v1:{self.plane}:{scope}:{normalized_email}".encode("utf-8")
        return hmac.new(self.settings.jwt_secret.encode("utf-8"), value, hashlib.sha256).hexdigest()

    @staticmethod
    def _timestamp(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)

    def _raise_login_lock(self, locked_until: datetime, now: datetime) -> None:
        retry_after = max(1, math.ceil((locked_until - now).total_seconds()))
        raise DomainError(
            "LOGIN_RATE_LIMITED",
            "Muitas tentativas de autenticação. Aguarde antes de tentar novamente.",
            429,
            "Tentativas temporariamente limitadas",
            headers={"Retry-After": str(retry_after)},
        )

    def _enforce_login_lock(self, identifier_hash: str, now: datetime) -> None:
        row = self.store.fetch_one(
            "SELECT locked_until FROM auth_login_attempts WHERE identifier_hash=?",
            (identifier_hash,),
        )
        if row and row["locked_until"]:
            locked_until = self._timestamp(row["locked_until"])
            if locked_until > now:
                self._raise_login_lock(locked_until, now)

    def _record_failed_login(self, identifier_hash: str, now: datetime) -> None:
        lock_window = timedelta(minutes=self.settings.login_lockout_minutes)
        cutoff = (now - lock_window).isoformat()
        locked_until = (now + lock_window).isoformat()
        retention = (now - max(timedelta(days=1), lock_window * 2)).isoformat()
        initial_lock = locked_until if self.settings.login_max_attempts <= 1 else None
        with self.store.transaction() as conn:
            # Identificadores aleatórios não podem fazer esta tabela crescer sem limite temporal.
            conn.execute("DELETE FROM auth_login_attempts WHERE updated_at<?", (retention,))
            conn.execute(
                """INSERT INTO auth_login_attempts(
                       identifier_hash,tenant_id,failed_attempts,window_started_at,locked_until,updated_at
                   ) VALUES(?,?,1,?,?,?)
                   ON CONFLICT(identifier_hash) DO UPDATE SET
                       tenant_id=excluded.tenant_id,
                       failed_attempts=CASE
                           WHEN auth_login_attempts.window_started_at<? THEN 1
                           ELSE auth_login_attempts.failed_attempts+1
                       END,
                       window_started_at=CASE
                           WHEN auth_login_attempts.window_started_at<? THEN excluded.window_started_at
                           ELSE auth_login_attempts.window_started_at
                       END,
                       locked_until=CASE
                           WHEN auth_login_attempts.window_started_at<? THEN NULL
                           WHEN auth_login_attempts.failed_attempts+1>=? THEN ?
                           ELSE NULL
                       END,
                       updated_at=excluded.updated_at""",
                (
                    identifier_hash,
                    self.tenant_id,
                    now.isoformat(),
                    initial_lock,
                    now.isoformat(),
                    cutoff,
                    cutoff,
                    cutoff,
                    self.settings.login_max_attempts,
                    locked_until,
                ),
            )
            row = conn.execute(
                "SELECT locked_until FROM auth_login_attempts WHERE identifier_hash=?",
                (identifier_hash,),
            ).fetchone()
        if row and row["locked_until"]:
            self._raise_login_lock(self._timestamp(row["locked_until"]), now)

    def _build_tokens(
        self,
        user_id: str,
        email: str,
        roles: tuple[str, ...],
        *,
        family_id: str | None = None,
    ) -> tuple[dict[str, Any], tuple[str, str, str | None, str, str, str, str]]:
        now = datetime.now(UTC)
        access_exp = now + timedelta(minutes=self.settings.access_token_minutes)
        access_jti = uuid7()
        refresh_jti = uuid7()
        session_id = family_id or refresh_jti
        claims = {
            "sub": user_id, "email": email, "roles": list(roles), "tid": self.tenant_id,
            "plane": self.plane, "iss": self.settings.jwt_issuer, "aud": f"pige360:{self.plane}",
            "iat": int(now.timestamp()), "nbf": int(now.timestamp()), "exp": int(access_exp.timestamp()),
            "jti": access_jti, "sid": session_id,
        }
        access = jwt.encode(claims, self.settings.jwt_secret, algorithm="HS256")
        refresh = secrets.token_urlsafe(48)
        refresh_hash = hashlib.sha256(refresh.encode()).hexdigest()
        refresh_exp = now + timedelta(days=self.settings.refresh_token_days)
        result = {
            "token_type": "Bearer", "access_token": access, "expires_in": self.settings.access_token_minutes * 60,
            "refresh_token": f"{refresh_jti}.{refresh}", "refresh_expires_at": refresh_exp.isoformat(),
        }
        record = (
            refresh_jti,
            user_id,
            self.tenant_id,
            refresh_hash,
            session_id,
            refresh_exp.isoformat(),
            iso_now(),
        )
        return result, record

    def _tokens(self, user_id: str, email: str, roles: tuple[str, ...]) -> dict[str, Any]:
        result, record = self._build_tokens(user_id, email, roles)
        with self.store.transaction() as conn:
            conn.execute(
                """INSERT INTO refresh_tokens(
                       jti,user_id,tenant_id,token_hash,family_id,expires_at,created_at
                   ) VALUES(?,?,?,?,?,?,?)""",
                record,
            )
        return result

    def _revoke_family(self, family_id: str, user_id: str) -> None:
        self.store.execute(
            """UPDATE refresh_tokens
               SET revoked_at=COALESCE(revoked_at, ?)
               WHERE family_id=? AND user_id=? AND tenant_id IS ?""",
            (iso_now(), family_id, user_id, self.tenant_id),
        )

    def rotate_refresh(self, token: str) -> dict[str, Any]:
        try:
            jti, secret = token.split(".", 1)
        except ValueError as exc:
            raise DomainError("INVALID_REFRESH_TOKEN", "Refresh token inválido.", 401) from exc
        digest = hashlib.sha256(secret.encode()).hexdigest()
        row = self.store.fetch_one("SELECT * FROM refresh_tokens WHERE jti=?", (jti,))
        if (
            not row
            or row.get("tenant_id") != self.tenant_id
            or not secrets.compare_digest(row["token_hash"], digest)
        ):
            raise DomainError("INVALID_REFRESH_TOKEN", "Refresh token inválido ou revogado.", 401)
        family_id = row.get("family_id") or row["jti"]
        if row["revoked_at"]:
            # A reutilização comprovada de um token rotacionado encerra todos
            # os descendentes daquela sessão, inclusive tokens de acesso.
            if row.get("replaced_by"):
                self._revoke_family(family_id, row["user_id"])
            raise DomainError("INVALID_REFRESH_TOKEN", "Refresh token inválido ou revogado.", 401)
        if self._timestamp(row["expires_at"]) <= datetime.now(UTC):
            self._revoke_family(family_id, row["user_id"])
            raise DomainError("EXPIRED_REFRESH_TOKEN", "Refresh token expirado.", 401)
        user = self.store.fetch_one(
            "SELECT * FROM users WHERE id=? AND tenant_id IS ? AND active=1",
            (row["user_id"], self.tenant_id),
        )
        if not user:
            self._revoke_family(family_id, row["user_id"])
            raise DomainError("USER_DISABLED", "Usuário indisponível.", 401)
        result, new_record = self._build_tokens(
            user["id"],
            user["email"],
            tuple(json.loads(user["roles_json"])),
            family_id=family_id,
        )
        new_jti = new_record[0]
        rotated = False
        with self.store.transaction() as conn:
            changed = conn.execute(
                """UPDATE refresh_tokens SET revoked_at=?, replaced_by=?
                   WHERE jti=? AND token_hash=? AND revoked_at IS NULL""",
                (iso_now(), new_jti, jti, digest),
            ).rowcount
            if changed == 1:
                conn.execute(
                    """INSERT INTO refresh_tokens(
                           jti,user_id,tenant_id,token_hash,family_id,expires_at,created_at
                       ) VALUES(?,?,?,?,?,?,?)""",
                    new_record,
                )
                rotated = True
            else:
                # A revogação do replay é confirmada na mesma transação que
                # observou a perda da rotação concorrente.
                conn.execute(
                    """UPDATE refresh_tokens
                       SET revoked_at=COALESCE(revoked_at, ?)
                       WHERE family_id=? AND user_id=? AND tenant_id IS ?""",
                    (iso_now(), family_id, row["user_id"], self.tenant_id),
                )
        if not rotated:
            # Outro processo venceu a rotação: o segundo uso é replay e a
            # família completa já foi invalidada atomicamente acima.
            raise DomainError("INVALID_REFRESH_TOKEN", "Refresh token inválido ou revogado.", 401)
        return result

    def revoke_session(self, user: CurrentUser, refresh_token: str | None = None) -> None:
        family_ids = {user.session_id} if user.session_id else set()
        # O access token identifica inequivocamente a sessão atual. O refresh
        # recebido no corpo só é usado como compatibilidade para access tokens
        # antigos, ainda sem claim `sid`; assim um cliente não encerra outra
        # sessão própria ao enviar por engano o refresh token errado.
        if not family_ids and refresh_token:
            try:
                jti, secret = refresh_token.split(".", 1)
            except ValueError:
                jti = secret = ""
            row = self.store.fetch_one("SELECT * FROM refresh_tokens WHERE jti=?", (jti,)) if jti else None
            digest = hashlib.sha256(secret.encode()).hexdigest() if secret else ""
            if (
                row
                and row["user_id"] == user.id
                and row.get("tenant_id") == self.tenant_id
                and secrets.compare_digest(row["token_hash"], digest)
            ):
                family_ids.add(row.get("family_id") or row["jti"])
        for family_id in family_ids:
            if family_id:
                self._revoke_family(family_id, user.id)


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
    session_id = claims.get("sid")
    if session_id is not None and (not isinstance(session_id, str) or not session_id):
        raise DomainError("INVALID_TOKEN", "Token de acesso inválido.", 401, "Não autenticado")
    if session_id:
        active_refreshes = request.state.store.fetch_all(
            """SELECT expires_at FROM refresh_tokens
               WHERE family_id=? AND user_id=? AND tenant_id IS ? AND revoked_at IS NULL""",
            (session_id, row["id"], resolution.tenant_id),
        )
        now = datetime.now(UTC)
        if not any(AuthService._timestamp(item["expires_at"]) > now for item in active_refreshes):
            raise DomainError("SESSION_REVOKED", "A sessão foi encerrada ou revogada.", 401, "Não autenticado")
    return CurrentUser(
        row["id"],
        resolution.tenant_id,
        row.get("person_id"),
        row["email"],
        tuple(json.loads(row["roles_json"])),
        resolution.plane,
        session_id,
    )


def require_roles(*roles: str) -> Callable[[CurrentUser], CurrentUser]:
    required = set(roles)
    def dependency(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if not user.has_any_role(required):
            raise DomainError("PERMISSION_DENIED", "Permissão insuficiente para esta operação.", 403, "Acesso negado")
        return user
    return dependency
