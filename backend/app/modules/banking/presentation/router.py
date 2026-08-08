from __future__ import annotations

import hashlib
import unicodedata
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.modules.finance.application.ledger import (
    apply_payment_allocations,
    installment_total_due,
    money,
    money_str,
)
from app.modules.operations.common import FINANCE_ROLES, dumps, require, row_or_404, tenant
from app.modules.portals.access import assert_financial_installment_access
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["banking"])


class BankAccountInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    bank_code: str | None = None
    branch: str | None = None
    account_number: str | None = None
    pix_key: str | None = None
    pix_receiver_name: str | None = Field(default=None, max_length=25)
    pix_receiver_city: str | None = Field(default=None, max_length=15)


class PixChargeInput(BaseModel):
    installment_id: str
    amount: Decimal | None = Field(default=None, gt=0)
    expires_in_minutes: int = Field(default=1440, ge=5, le=43200)


class PixConfirmInput(BaseModel):
    end_to_end_id: str = Field(min_length=8, max_length=200)
    paid_at: datetime | None = None


class BankImportInput(BaseModel):
    source_type: Literal["ofx", "cnab240", "cnab400", "csv", "api"]
    source_content: str = Field(min_length=1, max_length=5_000_000)
    transactions: list[dict[str, Any]] = Field(default_factory=list)


class BankReconciliationInput(BaseModel):
    payment_id: str
    reason: str = Field(min_length=3, max_length=2000)


def _tlv(tag: str, value: str) -> str:
    return f"{tag}{len(value):02d}{value}"


def _emv_text(value: str, max_length: int) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ASCII", "ignore").decode().upper()
    return " ".join(normalized.split())[:max_length]


def _crc16(payload: str) -> str:
    crc = 0xFFFF
    for byte in payload.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def _pix_brcode(key: str, name: str, city: str, amount: Decimal, txid: str) -> str:
    merchant = _tlv("00", "BR.GOV.BCB.PIX") + _tlv("01", key)
    additional = _tlv("05", txid[:25] or "***")
    body = (
        _tlv("00", "01")
        + _tlv("26", merchant)
        + _tlv("52", "0000")
        + _tlv("53", "986")
        + _tlv("54", money_str(amount))
        + _tlv("58", "BR")
        + _tlv("59", _emv_text(name, 25))
        + _tlv("60", _emv_text(city, 15))
        + _tlv("62", additional)
        + "6304"
    )
    return body + _crc16(body)


@router.get("/banking/accounts", operation_id="list_bank_accounts")
def list_accounts(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FINANCE_ROLES)
    return {
        "items": request.state.store.fetch_all(
            "SELECT * FROM bank_accounts WHERE tenant_id=? ORDER BY name",
            (tenant(user),),
        )
    }


@router.post("/banking/accounts", status_code=201, operation_id="create_bank_account")
def create_account(
    data: BankAccountInput,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, FINANCE_ROLES)
    tenant_id = tenant(user)
    now = iso_now()
    account_id = uuid7()
    receiver_name = _emv_text(data.pix_receiver_name or data.name, 25)
    receiver_city = _emv_text(data.pix_receiver_city or "SALVADOR", 15)
    with request.state.store.transaction() as conn:
        conn.execute(
            "INSERT INTO bank_accounts(id,tenant_id,name,bank_code,branch,account_number,pix_key,"
            "pix_receiver_name,pix_receiver_city,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                account_id,
                tenant_id,
                data.name,
                data.bank_code,
                data.branch,
                data.account_number,
                data.pix_key,
                receiver_name,
                receiver_city,
                "active",
                now,
                now,
            ),
        )
        result = {
            "id": account_id,
            "name": data.name,
            "pix_key": data.pix_key,
            "pix_receiver_name": receiver_name,
            "pix_receiver_city": receiver_city,
            "state": "active",
        }
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action="create",
            aggregate_type="bank_account",
            aggregate_id=account_id,
            correlation_id=request.state.correlation_id,
            after=result,
        )
    return result


@router.post(
    "/banking/accounts/{account_id}/pix-charges",
    status_code=201,
    operation_id="create_pix_charge",
)
def create_pix(
    account_id: str,
    data: PixChargeInput,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, FINANCE_ROLES | {"guardian"})
    tenant_id = tenant(user)
    account = row_or_404(
        request,
        "SELECT * FROM bank_accounts WHERE id=? AND tenant_id=? AND state='active'",
        (account_id, tenant_id),
        "BANK_ACCOUNT_NOT_FOUND",
        "Conta bancária não localizada.",
    )
    installment = (
        assert_financial_installment_access(request, user, data.installment_id)
        if "guardian" in user.roles
        else row_or_404(
            request,
            "SELECT * FROM installments WHERE id=? AND tenant_id=?",
            (data.installment_id, tenant_id),
            "INSTALLMENT_NOT_FOUND",
            "Parcela não localizada.",
        )
    )
    if not account["pix_key"]:
        raise DomainError("PIX_NOT_CONFIGURED", "Conta sem chave PIX configurada.", 409)

    balance = installment_total_due(installment) - money(installment["paid_amount"])
    amount = money(data.amount if data.amount is not None else balance)
    if amount <= 0 or amount > balance:
        raise DomainError("INVALID_PIX_AMOUNT", "Valor PIX inválido para o saldo da parcela.", 422)

    txid = uuid7().replace("-", "")[:25].upper()
    br_code = _pix_brcode(
        account["pix_key"],
        account["pix_receiver_name"] or account["name"],
        account["pix_receiver_city"] or "SALVADOR",
        amount,
        txid,
    )
    now = datetime.now(UTC)
    charge_id = uuid7()
    expires_at = (now + timedelta(minutes=data.expires_in_minutes)).isoformat()
    with request.state.store.transaction() as conn:
        conn.execute(
            "INSERT INTO pix_charges(id,tenant_id,bank_account_id,installment_id,txid,amount,br_code,"
            "state,expires_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                charge_id,
                tenant_id,
                account_id,
                data.installment_id,
                txid,
                money_str(amount),
                br_code,
                "pending",
                expires_at,
                now.isoformat(),
                now.isoformat(),
            ),
        )
        result = {
            "id": charge_id,
            "txid": txid,
            "installment_id": data.installment_id,
            "amount": money_str(amount),
            "br_code": br_code,
            "state": "pending",
            "expires_at": expires_at,
        }
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action="create",
            aggregate_type="pix_charge",
            aggregate_id=charge_id,
            correlation_id=request.state.correlation_id,
            after={key: value for key, value in result.items() if key != "br_code"},
        )
        add_outbox(
            conn,
            tenant_id=tenant_id,
            event_type="PixChargeCreated",
            aggregate_type="pix_charge",
            aggregate_id=charge_id,
            payload={"id": charge_id, "txid": txid, "amount": money_str(amount)},
            correlation_id=request.state.correlation_id,
        )
    return result


@router.post("/banking/pix-charges/{charge_id}/confirm", operation_id="confirm_pix_charge")
def confirm_pix(
    charge_id: str,
    data: PixConfirmInput,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, FINANCE_ROLES)
    tenant_id = tenant(user)
    paid_at = (data.paid_at or datetime.now(UTC)).isoformat()
    with request.state.store.transaction() as conn:
        charge = conn.execute(
            "SELECT * FROM pix_charges WHERE id=? AND tenant_id=?",
            (charge_id, tenant_id),
        ).fetchone()
        if not charge:
            raise DomainError("PIX_CHARGE_NOT_FOUND", "Cobrança PIX não localizada.", 404)
        if charge["state"] == "paid":
            existing = conn.execute(
                "SELECT payment_id FROM bank_transactions WHERE tenant_id=? AND external_id=?",
                (tenant_id, data.end_to_end_id),
            ).fetchone()
            return {
                "id": charge_id,
                "state": "paid",
                "payment_id": existing["payment_id"] if existing else None,
                "idempotent": True,
            }

        payment_id = uuid7()
        conn.execute(
            "INSERT INTO payments(id,tenant_id,method,amount,paid_at,external_reference,state,"
            "idempotency_key,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                payment_id,
                tenant_id,
                "pix",
                charge["amount"],
                paid_at,
                data.end_to_end_id,
                "confirmed",
                f"pix:{charge['txid']}",
                dumps({"txid": charge["txid"]}),
                iso_now(),
            ),
        )
        apply_payment_allocations(
            conn,
            tenant_id=tenant_id,
            payment_id=payment_id,
            allocations=[(charge["installment_id"], Decimal(str(charge["amount"])))],
            now=iso_now(),
        )
        conn.execute(
            "UPDATE pix_charges SET state='paid',paid_at=?,end_to_end_id=?,updated_at=? WHERE id=?",
            (paid_at, data.end_to_end_id, iso_now(), charge_id),
        )
        conn.execute(
            "INSERT INTO ledger_entries(id,tenant_id,entry_type,reference_type,reference_id,"
            "debit_account,credit_account,amount,occurred_at,description,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                uuid7(),
                tenant_id,
                "receipt",
                "payment",
                payment_id,
                "bank",
                "accounts_receivable",
                charge["amount"],
                paid_at,
                "Recebimento PIX",
                iso_now(),
            ),
        )
        result = {
            "id": charge_id,
            "state": "paid",
            "payment_id": payment_id,
            "end_to_end_id": data.end_to_end_id,
            "paid_at": paid_at,
        }
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action="confirm",
            aggregate_type="pix_charge",
            aggregate_id=charge_id,
            correlation_id=request.state.correlation_id,
            after=result,
        )
        add_outbox(
            conn,
            tenant_id=tenant_id,
            event_type="PaymentConfirmed",
            aggregate_type="payment",
            aggregate_id=payment_id,
            payload=result,
            correlation_id=request.state.correlation_id,
        )
    return result


@router.post(
    "/banking/accounts/{account_id}/imports",
    status_code=201,
    operation_id="import_bank_transactions",
)
def import_bank(
    account_id: str,
    data: BankImportInput,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, FINANCE_ROLES)
    tenant_id = tenant(user)
    row_or_404(
        request,
        "SELECT id FROM bank_accounts WHERE id=? AND tenant_id=?",
        (account_id, tenant_id),
        "BANK_ACCOUNT_NOT_FOUND",
        "Conta bancária não localizada.",
    )
    digest = hashlib.sha256(data.source_content.encode()).hexdigest()
    existing = request.state.store.fetch_one(
        "SELECT * FROM bank_imports WHERE tenant_id=? AND source_sha256=?",
        (tenant_id, digest),
    )
    if existing:
        return {
            "id": existing["id"],
            "source_sha256": digest,
            "idempotent": True,
            "transactions": 0,
        }

    import_id = uuid7()
    now = iso_now()
    count = 0
    with request.state.store.transaction() as conn:
        conn.execute(
            "INSERT INTO bank_imports(id,tenant_id,bank_account_id,source_type,source_sha256,imported_at,created_by) "
            "VALUES(?,?,?,?,?,?,?)",
            (import_id, tenant_id, account_id, data.source_type, digest, now, user.id),
        )
        for item in data.transactions:
            external_id = str(
                item.get("external_id") or hashlib.sha256(dumps(item).encode()).hexdigest()
            )
            posted_at = str(item.get("posted_at") or now)
            amount = money(item.get("amount", 0))
            direction = str(item.get("direction") or ("credit" if amount >= 0 else "debit"))
            cursor = conn.execute(
                "INSERT OR IGNORE INTO bank_transactions("
                "id,tenant_id,bank_import_id,bank_account_id,external_id,posted_at,description,amount,"
                "direction,state,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    uuid7(),
                    tenant_id,
                    import_id,
                    account_id,
                    external_id,
                    posted_at,
                    str(item.get("description") or ""),
                    money_str(abs(amount)),
                    direction,
                    "unmatched",
                    now,
                ),
            )
            if getattr(cursor, "rowcount", 1) != 0:
                count += 1
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action="import",
            aggregate_type="bank_import",
            aggregate_id=import_id,
            correlation_id=request.state.correlation_id,
            after={
                "source_type": data.source_type,
                "source_sha256": digest,
                "transactions": count,
            },
        )
    return {
        "id": import_id,
        "source_sha256": digest,
        "idempotent": False,
        "transactions": count,
    }


@router.get("/banking/transactions", operation_id="list_bank_transactions")
def list_bank_transactions(
    request: Request,
    account_id: str | None = None,
    state: Literal["unmatched", "matched"] | None = None,
    user: CurrentUser = Depends(current_user),
):
    require(user, FINANCE_ROLES)
    tenant_id = tenant(user)
    sql = "SELECT * FROM bank_transactions WHERE tenant_id=?"
    params: list[Any] = [tenant_id]
    if account_id:
        sql += " AND bank_account_id=?"
        params.append(account_id)
    if state:
        sql += " AND state=?"
        params.append(state)
    sql += " ORDER BY posted_at DESC,id DESC"
    return {"items": request.state.store.fetch_all(sql, params)}


@router.post(
    "/banking/transactions/{transaction_id}/reconcile",
    operation_id="reconcile_bank_transaction",
)
def reconcile_bank_transaction(
    transaction_id: str,
    data: BankReconciliationInput,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, FINANCE_ROLES)
    tenant_id = tenant(user)
    now = iso_now()
    with request.state.store.transaction() as conn:
        raw = conn.execute(
            "SELECT * FROM bank_transactions WHERE tenant_id=? AND id=?",
            (tenant_id, transaction_id),
        ).fetchone()
        if not raw:
            raise DomainError(
                "BANK_TRANSACTION_NOT_FOUND",
                "Transação bancária não localizada.",
                404,
            )
        transaction = dict(raw)
        if transaction["state"] == "matched":
            if transaction.get("payment_id") == data.payment_id:
                return {
                    "id": transaction_id,
                    "state": "matched",
                    "payment_id": data.payment_id,
                    "idempotent": True,
                }
            raise DomainError(
                "BANK_TRANSACTION_ALREADY_MATCHED",
                "Transação bancária já foi conciliada com outro pagamento.",
                409,
            )
        if transaction["direction"] != "credit":
            raise DomainError(
                "BANK_TRANSACTION_DIRECTION_NOT_SUPPORTED",
                "Somente créditos podem ser conciliados com recebimentos.",
                409,
            )
        payment_raw = conn.execute(
            "SELECT * FROM payments WHERE tenant_id=? AND id=?",
            (tenant_id, data.payment_id),
        ).fetchone()
        if not payment_raw:
            raise DomainError("PAYMENT_NOT_FOUND", "Pagamento não localizado.", 404)
        payment = dict(payment_raw)
        if payment["state"] not in {"confirmed", "partially_refunded", "refunded"}:
            raise DomainError(
                "PAYMENT_NOT_RECONCILABLE",
                "Pagamento não pode ser conciliado neste estado.",
                409,
            )
        if money(transaction["amount"]) != money(payment["amount"]):
            raise DomainError(
                "BANK_RECONCILIATION_AMOUNT_MISMATCH",
                "Valor da transação bancária difere do pagamento.",
                409,
            )
        conn.execute(
            "UPDATE bank_transactions SET state='matched',payment_id=?,matched_at=?,matched_by=?,"
            "reconciliation_reason=? WHERE tenant_id=? AND id=?",
            (data.payment_id, now, user.id, data.reason, tenant_id, transaction_id),
        )
        result = {
            "id": transaction_id,
            "state": "matched",
            "payment_id": data.payment_id,
            "matched_at": now,
            "matched_by": user.id,
            "reason": data.reason,
            "idempotent": False,
        }
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action="reconcile",
            aggregate_type="bank_transaction",
            aggregate_id=transaction_id,
            correlation_id=request.state.correlation_id,
            after=result,
            reason=data.reason,
        )
        add_outbox(
            conn,
            tenant_id=tenant_id,
            event_type="BankTransactionReconciled",
            aggregate_type="bank_transaction",
            aggregate_id=transaction_id,
            payload=result,
            correlation_id=request.state.correlation_id,
        )
    return result
