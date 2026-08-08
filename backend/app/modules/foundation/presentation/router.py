from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["foundation"])

@router.get("/health/live", operation_id="health_live")
def live() -> dict[str, str]:
    return {"status": "ok"}

@router.get("/health/ready", operation_id="health_ready")
def ready(request: Request) -> dict[str, str]:
    request.state.store.scalar("SELECT 1")
    return {"status": "ready", "plane": request.state.host_resolution.plane}

@router.get("/about", operation_id="about")
def about(request: Request) -> dict[str, object]:
    s = request.app.state.settings
    return {
        "name": s.app_name,
        "full_name": s.app_full_name,
        "version": s.version,
        "environment": s.environment,
        "plane": request.state.host_resolution.plane,
        "remote_operations": {
            "ci": s.remote_ci_enabled,
            "registry": s.remote_registry_enabled,
            "release": s.remote_release_enabled,
            "deploy": s.remote_deploy_enabled,
        },
    }
