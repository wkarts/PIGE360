from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from app.modules.foundation.application.metrics import PROMETHEUS_CONTENT_TYPE
from app.modules.foundation.application.readiness import build_readiness_report
from app.modules.foundation.presentation.schemas.readiness import ReadinessResponse

router = APIRouter(tags=["foundation"])

@router.get("/health/live", operation_id="health_live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/metrics", include_in_schema=False)
def metrics(request: Request) -> Response:
    return Response(
        content=request.app.state.metrics.render(),
        headers={
            "Cache-Control": "no-store",
            "Content-Type": PROMETHEUS_CONTENT_TYPE,
        },
    )

@router.get(
    "/health/ready",
    operation_id="health_ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse, "description": "Requisito crítico indisponível"}},
)
def ready(request: Request) -> JSONResponse:
    report = build_readiness_report(
        request.app.state.data_router,
        request.app.state.settings,
        probes=getattr(request.app.state, "readiness_probes", None),
        plane=request.state.host_resolution.plane,
    )
    return JSONResponse(report, status_code=200 if report["status"] == "ready" else 503)

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
