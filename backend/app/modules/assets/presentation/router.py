from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.modules.operations.common import SALES_ROLES, require, row_or_404, tenant
from app.shared.domain.ids import iso_now, uuid7
from app.shared.domain.money import money_str
from app.shared.events.records import add_audit
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["assets"])


class AssetInput(BaseModel):
    asset_number: str
    description: str
    acquisition_date: str | None = None
    acquisition_cost: Decimal | None = Field(default=None, ge=0)
    location: str | None = None
    responsible_person_id: str | None = None


@router.get("/assets", operation_id="list_assets_relational")
def list_assets(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, SALES_ROLES | {"unit_manager"})
    return {
        "items": request.state.store.fetch_all(
            "SELECT * FROM assets WHERE tenant_id=? ORDER BY asset_number",
            (tenant(user),),
        )
    }


@router.post("/assets", status_code=201, operation_id="create_asset_relational")
def create_asset(
    data: AssetInput,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, SALES_ROLES | {"unit_manager"})
    tenant_id = tenant(user)
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


class AssetEventInput(BaseModel):
    event_type: str
    to_location: str | None = None
    responsible_person_id: str | None = None
    cost: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)


@router.get("/assets/{asset_id}", operation_id="get_asset_details")
def get_asset(asset_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,SALES_ROLES|{"unit_manager"});tid=tenant(user)
    asset=request.state.store.fetch_one("SELECT * FROM assets WHERE tenant_id=? AND id=?",(tid,asset_id))
    if not asset:
        from app.shared.presentation.errors import DomainError
        raise DomainError("ASSET_NOT_FOUND","Patrimônio não localizado.",404)
    asset["events"]=request.state.store.fetch_all("SELECT * FROM asset_events WHERE tenant_id=? AND asset_id=? ORDER BY occurred_at DESC,id DESC",(tid,asset_id))
    return asset


@router.post("/assets/{asset_id}/events",status_code=201,operation_id="register_asset_event")
def register_asset_event(asset_id:str,data:AssetEventInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,SALES_ROLES|{"unit_manager"});tid=tenant(user);asset=row_or_404(request,"SELECT * FROM assets WHERE tenant_id=? AND id=?",(tid,asset_id),"ASSET_NOT_FOUND","Patrimônio não localizado.")
    if data.responsible_person_id:
        row_or_404(request,"SELECT id FROM people WHERE tenant_id=? AND id=?",(tid,data.responsible_person_id),"PERSON_NOT_FOUND","Responsável não localizado.")
    allowed={"move","maintenance_open","maintenance_complete","loan","return","writeoff"}
    if data.event_type not in allowed:
        from app.shared.presentation.errors import DomainError
        raise DomainError("INVALID_ASSET_EVENT","Evento patrimonial inválido.",422)
    now=iso_now();event_id=uuid7();new_state=asset["state"];new_location=asset.get("location");new_responsible=asset.get("responsible_person_id")
    if data.event_type=="move":
        if not data.to_location:
            from app.shared.presentation.errors import DomainError
            raise DomainError("ASSET_LOCATION_REQUIRED","Informe o novo local do patrimônio.",422)
        new_location=data.to_location
    elif data.event_type=="maintenance_open":new_state="maintenance"
    elif data.event_type=="maintenance_complete":new_state="active"
    elif data.event_type=="loan":new_state="loaned";new_responsible=data.responsible_person_id
    elif data.event_type=="return":new_state="active";new_responsible=None
    elif data.event_type=="writeoff":new_state="written_off"
    result={"id":event_id,"asset_id":asset_id,"event_type":data.event_type,"state":new_state,"location":new_location,"responsible_person_id":new_responsible}
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO asset_events(id,tenant_id,asset_id,event_type,from_location,to_location,responsible_person_id,cost,notes,state,occurred_at,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(event_id,tid,asset_id,data.event_type,asset.get("location"),data.to_location,data.responsible_person_id,money_str(data.cost) if data.cost is not None else None,data.notes,"completed",now,user.id))
        conn.execute("UPDATE assets SET state=?,location=?,responsible_person_id=?,updated_at=? WHERE tenant_id=? AND id=?",(new_state,new_location,new_responsible,now,tid,asset_id))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action=data.event_type,aggregate_type="asset",aggregate_id=asset_id,correlation_id=request.state.correlation_id,before={"state":asset["state"],"location":asset.get("location"),"responsible_person_id":asset.get("responsible_person_id")},after=result,reason=data.notes)
    return result
