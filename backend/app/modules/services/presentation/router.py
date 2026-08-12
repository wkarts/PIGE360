from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request, Response

from app.modules.operations.common import FINANCE_ROLES, require, tenant
from app.modules.services.application import vertical_service as service
from app.modules.services.presentation.vertical_schemas import (
    BillingRuleCreate,
    CatalogCreate,
    CatalogUpdate,
    CompetenceGenerate,
    ExecutionCancel,
    ExecutionComplete,
    ExecutionCreate,
    ExecutionStart,
    FiscalProfileCreate,
    FiscalProfilePublish,
    OrderCancel,
    OrderConfirm,
    PriceTableCreate,
    ServiceCreateUnified,
    ServiceOrderCreateUnified,
    ServiceUpdate,
    SubscriptionCreate,
    SubscriptionDecision,
    VariantCreate,
    VariantUpdate,
)
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["services"])

READ_ROLES = FINANCE_ROLES | {"secretary", "institution_director", "unit_manager", "auditor"}
WRITE_ROLES = FINANCE_ROLES | {"secretary", "institution_director", "unit_manager"}
CONFIG_ROLES = FINANCE_ROLES | {"institution_director", "unit_manager"}


def _created(response: Response, result: tuple[int, object]):
    status_code, payload = result
    response.status_code = status_code
    return payload


# Catálogos -----------------------------------------------------------------


@router.get("/service-catalogs", operation_id="list_service_catalogs")
def list_catalogs(
    request: Request,
    status: str | None = None,
    user: CurrentUser = Depends(current_user),
):
    require(user, READ_ROLES)
    return service.list_catalogs(request, tenant(user), status)


@router.post("/service-catalogs", status_code=201, operation_id="create_service_catalog")
def create_catalog(
    data: CatalogCreate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, CONFIG_ROLES)
    return _created(response, service.create_catalog(request, tenant(user), user, data, idempotency_key))


@router.get("/service-catalogs/{catalog_id}", operation_id="get_service_catalog")
def get_catalog(catalog_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, READ_ROLES)
    return service.catalog_detail(request, tenant(user), catalog_id)


@router.patch("/service-catalogs/{catalog_id}", operation_id="update_service_catalog")
def update_catalog(
    catalog_id: str,
    data: CatalogUpdate,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, CONFIG_ROLES)
    return service.update_catalog(request, tenant(user), user, catalog_id, data)


# Serviços, variações, preços e classificação fiscal ------------------------


@router.get("/services", operation_id="list_services_relational")
def list_services(
    request: Request,
    status: str | None = None,
    state: str | None = None,
    catalog_id: str | None = None,
    user: CurrentUser = Depends(current_user),
):
    require(user, READ_ROLES)
    return service.list_services(request, tenant(user), status or state, catalog_id)


@router.post("/services", status_code=201, operation_id="create_service_relational")
def create_service(
    data: ServiceCreateUnified,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, CONFIG_ROLES)
    return _created(response, service.create_service(request, tenant(user), user, data, idempotency_key))


@router.get("/services/{service_id}", operation_id="get_service_detail")
def get_service(service_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, READ_ROLES)
    return service.service_detail(request, tenant(user), service_id)


@router.patch("/services/{service_id}", operation_id="update_service")
def update_service(
    service_id: str,
    data: ServiceUpdate,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, CONFIG_ROLES)
    return service.update_service(request, tenant(user), user, service_id, data)


@router.post("/services/{service_id}/variants", status_code=201, operation_id="create_service_variant")
def create_variant(
    service_id: str,
    data: VariantCreate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, CONFIG_ROLES)
    return _created(response, service.create_variant(request, tenant(user), user, service_id, data, idempotency_key))


@router.patch("/service-variants/{variant_id}", operation_id="update_service_variant")
def update_variant(
    variant_id: str,
    data: VariantUpdate,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, CONFIG_ROLES)
    return service.update_variant(request, tenant(user), user, variant_id, data)


@router.post(
    "/services/{service_id}/fiscal-profiles",
    status_code=201,
    operation_id="create_service_fiscal_profile",
)
def create_fiscal_profile(
    service_id: str,
    data: FiscalProfileCreate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, CONFIG_ROLES)
    return _created(
        response,
        service.create_fiscal_profile(request, tenant(user), user, service_id, data, idempotency_key),
    )


@router.post(
    "/service-fiscal-profiles/{profile_id}/publish",
    operation_id="publish_service_fiscal_profile",
)
def publish_fiscal_profile(
    profile_id: str,
    data: FiscalProfilePublish,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, CONFIG_ROLES)
    return service.publish_fiscal_profile(request, tenant(user), user, profile_id, data.notes)


@router.post(
    "/services/{service_id}/price-tables",
    status_code=201,
    operation_id="create_service_price_table",
)
def create_price_table(
    service_id: str,
    data: PriceTableCreate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, CONFIG_ROLES)
    return _created(response, service.create_price(request, tenant(user), user, service_id, data, idempotency_key))


@router.post(
    "/services/{service_id}/billing-rules",
    status_code=201,
    operation_id="create_service_billing_rule",
)
def create_billing_rule(
    service_id: str,
    data: BillingRuleCreate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, CONFIG_ROLES)
    return _created(
        response,
        service.create_billing_rule(request, tenant(user), user, service_id, data, idempotency_key),
    )


# Assinaturas e competências -------------------------------------------------


@router.get("/service-subscriptions", operation_id="list_service_subscriptions")
def list_subscriptions(
    request: Request,
    status: str | None = None,
    person_id: str | None = None,
    user: CurrentUser = Depends(current_user),
):
    require(user, READ_ROLES)
    return service.list_subscriptions(request, tenant(user), status, person_id)


@router.post("/service-subscriptions", status_code=201, operation_id="create_service_subscription")
def create_subscription(
    data: SubscriptionCreate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, WRITE_ROLES)
    return _created(response, service.create_subscription(request, tenant(user), user, data, idempotency_key))


@router.get("/service-subscriptions/{subscription_id}", operation_id="get_service_subscription")
def get_subscription(
    subscription_id: str,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, READ_ROLES)
    return service.subscription_detail(request, tenant(user), subscription_id)


def _subscription_action(
    subscription_id: str,
    target: str,
    data: SubscriptionDecision,
    request: Request,
    user: CurrentUser,
):
    require(user, WRITE_ROLES)
    return service.change_subscription_status(request, tenant(user), user, subscription_id, target, data)


@router.post("/service-subscriptions/{subscription_id}/activate", operation_id="activate_service_subscription")
def activate_subscription(subscription_id: str, data: SubscriptionDecision, request: Request, user: CurrentUser = Depends(current_user)):
    return _subscription_action(subscription_id, "active", data, request, user)


@router.post("/service-subscriptions/{subscription_id}/suspend", operation_id="suspend_service_subscription")
def suspend_subscription(subscription_id: str, data: SubscriptionDecision, request: Request, user: CurrentUser = Depends(current_user)):
    return _subscription_action(subscription_id, "suspended", data, request, user)


@router.post("/service-subscriptions/{subscription_id}/resume", operation_id="resume_service_subscription")
def resume_subscription(subscription_id: str, data: SubscriptionDecision, request: Request, user: CurrentUser = Depends(current_user)):
    return _subscription_action(subscription_id, "active", data, request, user)


@router.post("/service-subscriptions/{subscription_id}/cancel", operation_id="cancel_service_subscription")
def cancel_subscription(subscription_id: str, data: SubscriptionDecision, request: Request, user: CurrentUser = Depends(current_user)):
    return _subscription_action(subscription_id, "cancelled", data, request, user)


@router.post(
    "/service-subscriptions/{subscription_id}/competencies",
    status_code=201,
    operation_id="generate_service_competence",
)
def generate_competence(
    subscription_id: str,
    data: CompetenceGenerate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, WRITE_ROLES)
    return _created(
        response,
        service.generate_competence(request, tenant(user), user, subscription_id, data, idempotency_key),
    )


# Pedidos e execução ---------------------------------------------------------


@router.get("/service-orders", operation_id="list_service_orders")
def list_orders(
    request: Request,
    status: str | None = None,
    state: str | None = None,
    enrollment_id: str | None = None,
    user: CurrentUser = Depends(current_user),
):
    require(user, READ_ROLES)
    return service.list_orders(request, tenant(user), status or state, enrollment_id)


@router.post("/service-orders", status_code=201, operation_id="create_service_order")
def create_order(
    data: ServiceOrderCreateUnified,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, WRITE_ROLES)
    return _created(response, service.create_order(request, tenant(user), user, data, idempotency_key))


@router.get("/service-orders/{order_id}", operation_id="get_service_order")
def get_order(order_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, READ_ROLES)
    return service.order_detail(request, tenant(user), order_id)


@router.post("/service-orders/{order_id}/confirm", operation_id="confirm_service_order")
def confirm_order(
    order_id: str,
    data: OrderConfirm,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, WRITE_ROLES)
    return service.confirm_order(request, tenant(user), user, order_id, data)


@router.post("/service-orders/{order_id}/start", operation_id="start_service_order")
def start_order(order_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, WRITE_ROLES)
    return service.start_order(request, tenant(user), user, order_id)


@router.post("/service-orders/{order_id}/complete", operation_id="complete_service_order")
def complete_order(order_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, WRITE_ROLES)
    return service.complete_order(request, tenant(user), user, order_id)


@router.post("/service-orders/{order_id}/cancel", operation_id="cancel_service_order")
def cancel_order(
    order_id: str,
    data: OrderCancel,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, WRITE_ROLES)
    return service.cancel_order(request, tenant(user), user, order_id, data)


@router.post(
    "/service-orders/{order_id}/executions",
    status_code=201,
    operation_id="create_service_execution",
)
def create_execution(
    order_id: str,
    data: ExecutionCreate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, WRITE_ROLES)
    return _created(
        response,
        service.create_execution(request, tenant(user), user, order_id, data, idempotency_key),
    )


@router.get("/service-executions", operation_id="list_service_executions")
def list_executions(
    request: Request,
    status: str | None = None,
    order_id: str | None = None,
    user: CurrentUser = Depends(current_user),
):
    require(user, READ_ROLES)
    return service.list_executions(request, tenant(user), status, order_id)


@router.post("/service-executions/{execution_id}/start", operation_id="start_service_execution")
def start_execution(
    execution_id: str,
    data: ExecutionStart,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, WRITE_ROLES)
    return service.start_execution(request, tenant(user), user, execution_id, data)


@router.post("/service-executions/{execution_id}/complete", operation_id="complete_service_execution")
def complete_execution(
    execution_id: str,
    data: ExecutionComplete,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, WRITE_ROLES)
    return service.complete_execution(request, tenant(user), user, execution_id, data)


@router.post("/service-executions/{execution_id}/cancel", operation_id="cancel_service_execution")
def cancel_execution(
    execution_id: str,
    data: ExecutionCancel,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, WRITE_ROLES)
    return service.cancel_execution(request, tenant(user), user, execution_id, data)


# Fiscal e indicadores -------------------------------------------------------


@router.get("/service-fiscal-events", operation_id="list_service_fiscal_events")
def list_fiscal_events(
    request: Request,
    status: str | None = None,
    order_id: str | None = None,
    user: CurrentUser = Depends(current_user),
):
    require(user, READ_ROLES)
    return service.list_fiscal_events(request, tenant(user), status, order_id)


@router.get("/services-dashboard", operation_id="get_services_dashboard")
def services_dashboard(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, READ_ROLES)
    return service.dashboard(request, tenant(user))
