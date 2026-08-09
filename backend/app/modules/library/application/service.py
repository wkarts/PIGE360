from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.shared.domain.ids import iso_now, uuid7

DEFAULT_POLICY={"code":"default","version":1,"max_loan_days":14,"max_renewals":2,"grace_days":0,"daily_fine":"0.00","reservation_hold_hours":48}


def ensure_policy(conn: Any, tenant_id: str, actor_id: str) -> dict[str, Any]:
    row=conn.execute("SELECT * FROM library_policies WHERE tenant_id=? AND state='active' AND effective_from<=? ORDER BY effective_from DESC,version DESC LIMIT 1",(tenant_id,iso_now()[:10])).fetchone()
    if row:return dict(row)
    now=iso_now();pid=uuid7()
    conn.execute("INSERT INTO library_policies(id,tenant_id,code,version,effective_from,max_loan_days,max_renewals,grace_days,daily_fine,reservation_hold_hours,state,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(pid,tenant_id,"default",1,"1970-01-01",14,2,0,"0.00",48,"active",actor_id,now,now))
    return {"id":pid,"tenant_id":tenant_id,**DEFAULT_POLICY,"effective_from":"1970-01-01","state":"active"}


def active_policy(store: Any, tenant_id: str) -> dict[str, Any] | None:
    return store.fetch_one("SELECT * FROM library_policies WHERE tenant_id=? AND state='active' AND effective_from<=? ORDER BY effective_from DESC,version DESC LIMIT 1",(tenant_id,iso_now()[:10]))


def promote_next_reservation(conn: Any, *, tenant_id: str, item_id: str, policy: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    row=conn.execute("SELECT * FROM library_reservations WHERE tenant_id=? AND library_item_id=? AND state='queued' ORDER BY queued_at LIMIT 1",(tenant_id,item_id)).fetchone()
    if not row:
        conn.execute("UPDATE library_items SET state='available',updated_at=? WHERE tenant_id=? AND id=?",(now.isoformat(),tenant_id,item_id));return None
    reservation=dict(row);expires=(now+timedelta(hours=int(policy["reservation_hold_hours"]))).isoformat()
    conn.execute("UPDATE library_reservations SET state='ready',ready_at=?,expires_at=? WHERE tenant_id=? AND id=?",(now.isoformat(),expires,tenant_id,reservation["id"]))
    conn.execute("UPDATE library_items SET state='reserved',updated_at=? WHERE tenant_id=? AND id=?",(now.isoformat(),tenant_id,item_id))
    reservation.update({"state":"ready","ready_at":now.isoformat(),"expires_at":expires});return reservation


def fine_for_return(*, due_at: str, returned_at: datetime, grace_days: int, daily_fine: Any) -> Decimal:
    due=datetime.fromisoformat(due_at)
    if due.tzinfo is None:due=due.replace(tzinfo=UTC)
    late_days=(returned_at.date()-due.astimezone(UTC).date()).days-int(grace_days)
    if late_days<=0:return Decimal("0.00")
    return (Decimal(str(daily_fine))*late_days).quantize(Decimal("0.01"))
