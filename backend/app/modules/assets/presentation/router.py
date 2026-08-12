from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, Field

from app.modules.assets.application import vertical_service as service
from app.modules.assets.presentation.vertical_schemas import (
    AssetCreate,
    AssetLoanCreate,
    AssetLoanReturn,
    AssetLocationCreate,
    AssetMaintenanceComplete,
    AssetMaintenanceCreate,
    AssetTransfer,
    DepreciationCalculate,
)
from app.modules.operations.common import SALES_ROLES, require, row_or_404, tenant
from app.shared.domain.ids import iso_now, uuid7
from app.shared.domain.money import money_str
from app.shared.events.records import add_audit
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["assets"])

ASSET_ROLES = SALES_ROLES | {"unit_manager", "finance_manager", "auditor"}
ASSET_WRITE_ROLES = SALES_ROLES | {"unit_manager"}


def _created(response: Response, result: tuple[int, object]):
    status_code, payload = result
    response.status_code = status_code
    return payload


# Localizações patrimoniais --------------------------------------------------


@router.get("/asset-locations", operation_id="list_asset_locations")
def list_asset_locations(
    request: Request,
    status: str | None = None,
    parent_id: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    user: CurrentUser = Depends(current_user),
):
    require(user, ASSET_ROLES)
    return service.list_locations(
        request,
        tenant(user),
        status=status,
        parent_id=parent_id,
        cursor=cursor,
        limit=limit,
    )


@router.post("/asset-locations", status_code=201, operation_id="create_asset_location")
def create_asset_location(
    data: AssetLocationCreate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(
        default=None, alias="Idempotency-Key", min_length=8, max_length=200
    ),
    user: CurrentUser = Depends(current_user),
):
    require(user, ASSET_WRITE_ROLES)
    return _created(
        response,
        service.create_location(request, tenant(user), user, data, idempotency_key),
    )


@router.get("/asset-locations/{location_id}", operation_id="get_asset_location")
def get_asset_location(
    location_id: str,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, ASSET_ROLES)
    return service.location_detail(request, tenant(user), location_id)


# Patrimônio ----------------------------------------------------------------


class AssetInput(BaseModel):
    """Contrato legado preservado para instalações já existentes."""

    asset_number: str
    description: str
    acquisition_date: str | None = None
    acquisition_cost: Decimal | None = Field(default=None, ge=0)
    location: str | None = None
    responsible_person_id: str | None = None


@router.get("/assets", operation_id="list_assets_relational")
def list_assets(
    request: Request,
    status: str | None = None,
    location_id: str | None = None,
    responsible_person_id: str | None = None,
    search: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    user: CurrentUser = Depends(current_user),
):
    require(user, ASSET_ROLES)
    return service.list_assets(
        request,
        tenant(user),
        status=status,
        location_id=location_id,
        responsible_person_id=responsible_person_id,
        search=search,
        cursor=cursor,
        limit=limit,
    )


@router.post("/assets", status_code=201, operation_id="create_asset_relational")
def create_asset(
    data: AssetInput | AssetCreate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(
        default=None, alias="Idempotency-Key", min_length=8, max_length=200
    ),
    user: CurrentUser = Depends(current_user),
):
    require(user, ASSET_WRITE_ROLES)
    tenant_id = tenant(user)
    if isinstance(data, AssetCreate):
        return _created(
            response,
            service.create_asset(request, tenant_id, user, data, idempotency_key),
        )

    if data.responsible_person_id:
        row_or_404(
            request,
            "SELECT id FROM people WHERE id=? AND tenant_id=?",
            (data.responsible_person_id, tenant_id),
            "PERSON_NOT_FOUND",
            "Responsável pelo patrimônio não localizado.",
        )
    asset_id = uuid7()
    now = iso_now()
    result = {
        "id": asset_id,
        "asset_number": data.asset_number,
        "description": data.description,
        "state": "active",
        "status": "active",
    }
    with request.state.store.transaction() as conn:
        conn.execute(
            "INSERT INTO assets(id,tenant_id,asset_number,description,acquisition_date,acquisition_cost,"
            "location,responsible_person_id,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                asset_id,
                tenant_id,
                data.asset_number,
                data.description,
                data.acquisition_date,
                money_str(data.acquisition_cost) if data.acquisition_cost is not None else None,
                data.location,
                data.responsible_person_id,
                "active",
                now,
                now,
            ),
        )
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action="create",
            aggregate_type="asset",
            aggregate_id=asset_id,
            correlation_id=request.state.correlation_id,
            after=result,
        )
    return result


@router.get("/assets/{asset_id}", operation_id="get_asset_details")
def get_asset(
    asset_id: str,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, ASSET_ROLES)
    tenant_id = tenant(user)
    detail = service.asset_detail(request, tenant_id, asset_id)
    # Resposta híbrida: mantém os campos planos e `events` do contrato legado,
    # além de expor os agregados verticais estruturados.
    events = request.state.store.fetch_all(
        "SELECT * FROM asset_events WHERE tenant_id=? AND asset_id=? ORDER BY occurred_at DESC,id DESC",
        (tenant_id, asset_id),
    )
    return {
        **detail["asset"],
        **detail,
        "events": events,
    }


@router.post("/assets/{asset_id}/transfers", operation_id="transfer_asset")
def transfer_asset(
    asset_id: str,
    data: AssetTransfer,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, ASSET_WRITE_ROLES)
    return service.transfer_asset(request, tenant(user), user, asset_id, data)


@router.post("/assets/{asset_id}/maintenances", status_code=201, operation_id="create_asset_maintenance")
def create_asset_maintenance(
    asset_id: str,
    data: AssetMaintenanceCreate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(
        default=None, alias="Idempotency-Key", min_length=8, max_length=200
    ),
    user: CurrentUser = Depends(current_user),
):
    require(user, ASSET_WRITE_ROLES)
    return _created(
        response,
        service.create_maintenance(
            request, tenant(user), user, asset_id, data, idempotency_key
        ),
    )


@router.post("/asset-maintenances/{maintenance_id}/start", operation_id="start_asset_maintenance")
def start_asset_maintenance(
    maintenance_id: str,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, ASSET_WRITE_ROLES)
    return service.start_maintenance(request, tenant(user), user, maintenance_id)


@router.post("/asset-maintenances/{maintenance_id}/complete", operation_id="complete_asset_maintenance")
def complete_asset_maintenance(
    maintenance_id: str,
    data: AssetMaintenanceComplete,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, ASSET_WRITE_ROLES)
    return service.complete_maintenance(
        request, tenant(user), user, maintenance_id, data
    )


@router.post("/assets/{asset_id}/loans", status_code=201, operation_id="create_asset_loan")
def create_asset_loan(
    asset_id: str,
    data: AssetLoanCreate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(
        default=None, alias="Idempotency-Key", min_length=8, max_length=200
    ),
    user: CurrentUser = Depends(current_user),
):
    require(user, ASSET_WRITE_ROLES)
    return _created(
        response,
        service.create_loan(
            request, tenant(user), user, asset_id, data, idempotency_key
        ),
    )


@router.post("/asset-loans/{loan_id}/return", operation_id="return_asset_loan")
def return_asset_loan(
    loan_id: str,
    data: AssetLoanReturn,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, ASSET_WRITE_ROLES)
    return service.return_loan(request, tenant(user), user, loan_id, data)


@router.post("/assets/{asset_id}/depreciations", status_code=201, operation_id="calculate_asset_depreciation")
def calculate_asset_depreciation(
    asset_id: str,
    data: DepreciationCalculate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(
        default=None, alias="Idempotency-Key", min_length=8, max_length=200
    ),
    user: CurrentUser = Depends(current_user),
):
    require(user, ASSET_WRITE_ROLES)
    return _created(
        response,
        service.calculate_depreciation(
            request, tenant(user), user, asset_id, data, idempotency_key
        ),
    )


# Eventos legados ------------------------------------------------------------


class AssetEventInput(BaseModel):
    event_type: str
    to_location: str | None = None
    responsible_person_id: str | None = None
    cost: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)


@router.post("/assets/{asset_id}/events", status_code=201, operation_id="register_asset_event")
def register_asset_event(
    asset_id: str,
    data: AssetEventInput,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, ASSET_WRITE_ROLES)
    tenant_id = tenant(user)
    asset = row_or_404(
        request,
        "SELECT * FROM assets WHERE tenant_id=? AND id=?",
        (tenant_id, asset_id),
        "ASSET_NOT_FOUND",
        "Patrimônio não localizado.",
    )
    if data.responsible_person_id:
        row_or_404(
            request,
            "SELECT id FROM people WHERE tenant_id=? AND id=?",
            (tenant_id, data.responsible_person_id),
            "PERSON_NOT_FOUND",
            "Responsável não localizado.",
        )
    allowed = {"move", "maintenance_open", "maintenance_complete", "loan", "return", "writeoff"}
    if data.event_type not in allowed:
        raise DomainError("INVALID_ASSET_EVENT", "Evento patrimonial inválido.", 422)
    now = iso_now()
    event_id = uuid7()
    new_state = asset["state"]
    new_location = asset.get("location")
    new_responsible = asset.get("responsible_person_id")
    if data.event_type == "move":
        if not data.to_location:
            raise DomainError("ASSET_LOCATION_REQUIRED", "Informe o novo local do patrimônio.", 422)
        new_location = data.to_location
    elif data.event_type == "maintenance_open":
        new_state = "maintenance"
    elif data.event_type == "maintenance_complete":
        new_state = "active"
    elif data.event_type == "loan":
        new_state = "loaned"
        new_responsible = data.responsible_person_id
    elif data.event_type == "return":
        new_state = "active"
        new_responsible = None
    elif data.event_type == "writeoff":
        new_state = "written_off"
    result = {
        "id": event_id,
        "asset_id": asset_id,
        "event_type": data.event_type,
        "state": new_state,
        "status": new_state,
        "location": new_location,
        "responsible_person_id": new_responsible,
    }
    with request.state.store.transaction() as conn:
        conn.execute(
            "INSERT INTO asset_events(id,tenant_id,asset_id,event_type,from_location,to_location,responsible_person_id,cost,notes,state,occurred_at,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                event_id,
                tenant_id,
                asset_id,
                data.event_type,
                asset.get("location"),
                data.to_location,
                data.responsible_person_id,
                money_str(data.cost) if data.cost is not None else None,
                data.notes,
                "completed",
                now,
                user.id,
            ),
        )
        conn.execute(
            "UPDATE assets SET state=?,location=?,responsible_person_id=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?",
            (new_state, new_location, new_responsible, now, tenant_id, asset_id),
        )
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action=data.event_type,
            aggregate_type="asset",
            aggregate_id=asset_id,
            correlation_id=request.state.correlation_id,
            before={
                "state": asset["state"],
                "location": asset.get("location"),
                "responsible_person_id": asset.get("responsible_person_id"),
            },
            after=result,
            reason=data.notes,
        )
    return result
