from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.bootstrap.config import Settings
from app.bootstrap.demo import seed_demo
from app.modules.app_factory.presentation.router import router as app_factory_router
from app.modules.academic.presentation.router import router as academic_progress_router
from app.modules.branding.presentation.router import router as branding_router
from app.modules.class_attendance.presentation.router import router as attendance_router
from app.modules.canteen.presentation.router import router as canteen_router
from app.modules.contracts.presentation.router import router as contracts_router
from app.modules.foundation.application.metrics import HttpMetricsMiddleware, MetricsRegistry
from app.modules.foundation.presentation.router import router as foundation_router
from app.modules.fiscal.presentation.router import router as fiscal_ibpt_router
from app.modules.identity.presentation.router import router as identity_router
from app.modules.integrations.presentation.router import router as integrations_router
from app.modules.integrations.presentation.connect_api_router import router as connect_api_router
from app.modules.lesson_planning.presentation.router import router as planning_router
from app.modules.pedagogy.presentation.router import router as pedagogy_router
from app.modules.mail.presentation.router import router as mail_router
from app.modules.library.presentation.router import router as library_router
from app.modules.transportation.presentation.router import router as transportation_router
from app.modules.health.presentation.router import router as health_router
from app.modules.reporting.presentation.router import router as reporting_router
from app.modules.analytics.presentation.router import router as analytics_router
from app.modules.communication.presentation.router import router as communication_router
from app.modules.commercial_administration.presentation.router import router as commercial_administration_router
from app.modules.compliance.presentation.router import router as compliance_router
from app.modules.notices.presentation.router import router as notices_router
from app.modules.requests.presentation.router import router as requests_router
from app.modules.workflows.presentation.router import router as workflows_router
from app.modules.operations.academic_core import router as academic_core_router
from app.modules.finance.presentation.router import router as finance_router
from app.modules.banking.presentation.router import router as banking_router
from app.modules.services.presentation.router import router as services_router
from app.modules.inventory.presentation.router import router as inventory_router
from app.modules.pos.presentation.router import router as pos_router
from app.modules.sales.presentation.router import router as sales_router
from app.modules.procurement.presentation.router import router as procurement_router
from app.modules.assets.presentation.router import router as assets_router
from app.modules.hr.presentation.router import router as hr_router
from app.modules.payroll.presentation.router import router as payroll_router
from app.modules.personnel.presentation.router import router as personnel_router
from app.modules.timekeeping.presentation.router import router as timekeeping_router
from app.modules.operations.community_operations import router as community_operations_router
from app.modules.government_education.presentation.router import router as government_education_router
from app.modules.admissions.presentation.router import router as admissions_router
from app.modules.portals.presentation.router import router as portals_router
from app.modules.tenancy.presentation.router import router as tenancy_router
from app.modules.tenancy.presentation.domain_router import router as tenancy_domain_router
from app.modules.platform_operations.presentation.logs_router import router as platform_logs_router
from app.modules.platform_operations.presentation.router import router as platform_operations_router
from app.modules.operational_control.presentation.router import router as operational_control_router
from app.shared.database.router import DataRouter
from app.shared.presentation.errors import DomainError, domain_error_handler, problem, unhandled_error_handler
from app.shared.security.middleware import RequestContextMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    data_router = DataRouter(settings)
    metrics = MetricsRegistry(environment=settings.environment, version=settings.version)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        data_router.initialize()
        if settings.demo_mode:
            from pathlib import Path

            seed_demo(data_router, settings, Path(__file__).resolve().parents[2])
        try:
            yield
        finally:
            data_router.close()

    app = FastAPI(
        title=settings.app_full_name,
        version=settings.version,
        description="API REST multi-tenant do PIGE360",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.data_router = data_router
    app.state.metrics = metrics

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Correlation-ID"],
        )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(HttpMetricsMiddleware, registry=metrics)
    app.add_exception_handler(DomainError, domain_error_handler)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        errors = []
        for item in exc.errors():
            errors.append(
                {
                    "field": ".".join(str(x) for x in item["loc"] if x not in {"body", "query", "path"}),
                    "code": item["type"].upper(),
                    "message": item["msg"],
                }
            )
        error = DomainError(
            "VALIDATION_ERROR",
            "Existem campos inválidos.",
            422,
            "Erro de validação",
            errors,
        )
        return JSONResponse(problem(error, getattr(request.state, "correlation_id", None)), status_code=422)

    if settings.environment not in {"development", "testing"}:
        app.add_exception_handler(Exception, unhandled_error_handler)

    api_prefix = "/api/v1"
    for router in [
        foundation_router,
        identity_router,
        tenancy_router,
        tenancy_domain_router,
        branding_router,
        app_factory_router,
        academic_core_router,
        admissions_router,
        academic_progress_router,
        finance_router,
        banking_router,
        services_router,
        inventory_router,
        canteen_router,
        pos_router,
        sales_router,
        procurement_router,
        assets_router,
        hr_router,
        personnel_router,
        payroll_router,
        timekeeping_router,
        community_operations_router,
        government_education_router,
        portals_router,
        planning_router,
        pedagogy_router,
        attendance_router,
        contracts_router,
        integrations_router,
        connect_api_router,
        mail_router,
        library_router,
        transportation_router,
        health_router,
        reporting_router,
        analytics_router,
        communication_router,
        commercial_administration_router,
        compliance_router,
        notices_router,
        requests_router,
        workflows_router,
        fiscal_ibpt_router,
        platform_operations_router,
        platform_logs_router,
        operational_control_router,
    ]:
        app.include_router(router, prefix=api_prefix)
    return app


app = create_app()
