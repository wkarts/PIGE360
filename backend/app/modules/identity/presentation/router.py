from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field
from fastapi import APIRouter, Depends, Header, Request, Response

from app.shared.security.auth import AuthService, CurrentUser, current_user, require_roles
from app.shared.presentation.errors import DomainError
from app.shared.tenant_quotas import tenant_quota_limit

router = APIRouter(prefix="/auth", tags=["identity"])

class LoginInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)

class RefreshInput(BaseModel):
    refresh_token: str = Field(min_length=20)

class LogoutInput(BaseModel):
    refresh_token: str | None = Field(default=None, min_length=20, max_length=1024)

class CreateUserInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=1024)
    roles: list[str] = Field(min_length=1)
    person_id: str | None = None

@router.post("/login", operation_id="auth_login")
def login(data: LoginInput, request: Request):
    r = request.state.host_resolution
    return AuthService(request.state.store, request.app.state.settings, tenant_id=r.tenant_id, plane=r.plane).login(str(data.email), data.password)

@router.post("/refresh", operation_id="auth_refresh")
def refresh(data: RefreshInput, request: Request):
    r = request.state.host_resolution
    return AuthService(request.state.store, request.app.state.settings, tenant_id=r.tenant_id, plane=r.plane).rotate_refresh(data.refresh_token)

@router.post("/logout", operation_id="auth_logout", status_code=204)
def logout(
    request: Request,
    data: LogoutInput | None = None,
    user: CurrentUser = Depends(current_user),
):
    r = request.state.host_resolution
    AuthService(
        request.state.store,
        request.app.state.settings,
        tenant_id=r.tenant_id,
        plane=r.plane,
    ).revoke_session(user, data.refresh_token if data else None)
    return Response(status_code=204)

@router.get("/me", operation_id="auth_me")
def me(user: CurrentUser = Depends(current_user)):
    return {"id": user.id, "tenant_id": user.tenant_id, "person_id": user.person_id, "email": user.email, "roles": user.roles, "plane": user.plane}

@router.post("/users", operation_id="auth_create_user", status_code=201)
def create_user(data: CreateUserInput, request: Request, user: CurrentUser = Depends(require_roles("platform_super_admin", "tenant_owner"))):
    r = request.state.host_resolution
    max_active_users = (
        tenant_quota_limit(request.app.state.data_router.control, r.tenant_id, "max_users")
        if r.plane == "tenant" and r.tenant_id
        else None
    )
    return AuthService(request.state.store, request.app.state.settings, tenant_id=r.tenant_id, plane=r.plane).create_user(
        str(data.email),
        data.password,
        data.roles,
        data.person_id,
        max_active_users=max_active_users,
    )
