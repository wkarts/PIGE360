from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app.modules.operations.common import tenant
from app.modules.reporting.application.catalog import definition, public_catalog
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.reporting import render_csv, render_pdf, render_xlsx
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["reporting"])


class ReportRunInput(BaseModel):
    report_code: str = Field(min_length=2, max_length=100)
    format: Literal["pdf","xlsx","csv"] = "pdf"
    parameters: dict[str, Any] = Field(default_factory=dict)


def _rows(request: Request, tid: str, code: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    if code == "enrollments":
        sql = """SELECT e.enrollment_number AS registration_number,p.full_name AS student_name,cg.name AS class_name,pr.name AS program_name,e.state,e.enrolled_on AS starts_on,e.ended_on AS ends_on FROM enrollments e JOIN students s ON s.id=e.student_id AND s.tenant_id=e.tenant_id JOIN people p ON p.id=s.person_id AND p.tenant_id=e.tenant_id JOIN class_groups cg ON cg.id=e.class_group_id AND cg.tenant_id=e.tenant_id JOIN programs pr ON pr.id=e.program_id AND pr.tenant_id=e.tenant_id WHERE e.tenant_id=?"""
        values: list[Any] = [tid]
        if params.get("class_group_id"): sql += " AND e.class_group_id=?"; values.append(str(params["class_group_id"]))
        if params.get("state"): sql += " AND e.state=?"; values.append(str(params["state"]))
        return request.state.store.fetch_all(sql + " ORDER BY p.full_name", values)
    if code == "finance_receivables":
        sql = """SELECT p.full_name AS student_name,e.enrollment_number AS contract_number,i.sequence AS installment_number,i.due_date,i.original_amount AS amount,i.paid_amount,(CAST(i.original_amount AS NUMERIC)+CAST(i.penalty_amount AS NUMERIC)+CAST(i.interest_amount AS NUMERIC)-CAST(i.discount_amount AS NUMERIC)-CAST(i.paid_amount AS NUMERIC)) AS balance,i.state FROM installments i JOIN financial_contracts fc ON fc.id=i.financial_contract_id AND fc.tenant_id=i.tenant_id LEFT JOIN enrollments e ON e.id=fc.enrollment_id AND e.tenant_id=fc.tenant_id LEFT JOIN students s ON s.id=e.student_id AND s.tenant_id=e.tenant_id LEFT JOIN people p ON p.id=s.person_id AND p.tenant_id=e.tenant_id WHERE i.tenant_id=?"""
        values=[tid]
        if params.get("state"): sql += " AND i.state=?"; values.append(str(params["state"]))
        return request.state.store.fetch_all(sql + " ORDER BY i.due_date,fc.contract_number,i.installment_number", values)
    if code == "attendance_summary":
        return request.state.store.fetch_all("""SELECT p.full_name AS student_name,s.registration_number,COUNT(ar.id) AS total_records,SUM(CASE WHEN ar.status_code IN ('present','remote_present','activity_present') THEN 1 ELSE 0 END) AS present_count,SUM(CASE WHEN ar.status_code IN ('absent','justified_absence','excused_absence','medical_leave','institutional_leave') THEN 1 ELSE 0 END) AS absence_count,SUM(CASE WHEN ar.status_code IN ('late','late_justified') THEN 1 ELSE 0 END) AS late_count FROM students s JOIN people p ON p.id=s.person_id AND p.tenant_id=s.tenant_id LEFT JOIN attendance_records ar ON ar.student_id=s.id AND ar.tenant_id=s.tenant_id WHERE s.tenant_id=? GROUP BY s.id,p.full_name,s.registration_number ORDER BY p.full_name""",(tid,))
    if code == "inventory_stock":
        return request.state.store.fetch_all("""SELECT p.sku,p.name AS product_name,sb.warehouse,sb.quantity,sb.updated_at FROM stock_balances sb JOIN products p ON p.id=sb.product_id AND p.tenant_id=sb.tenant_id WHERE sb.tenant_id=? ORDER BY p.name,sb.warehouse""",(tid,))
    if code == "payroll_run":
        run_id=str(params["run_id"])
        if not request.state.store.fetch_one("SELECT id FROM payroll_runs WHERE tenant_id=? AND id=?",(tid,run_id)):
            raise DomainError("PAYROLL_RUN_NOT_FOUND","Folha não localizada.",404)
        return request.state.store.fetch_all("""SELECT p.full_name AS employee_name,e.employee_number,pe.gross_amount,pe.deductions_amount AS discount_amount,pe.net_amount,pe.state FROM payroll_entries pe JOIN employees e ON e.id=pe.employee_id AND e.tenant_id=pe.tenant_id JOIN people p ON p.id=e.person_id AND p.tenant_id=e.tenant_id WHERE pe.tenant_id=? AND pe.payroll_run_id=? ORDER BY p.full_name""",(tid,run_id))
    if code == "teaching_plan_coverage":
        return request.state.store.fetch_all("""SELECT cg.name AS class_name,cc.name AS component_name,tp.title,tp.status,tp.current_version AS version,ap.name AS period_label FROM teaching_plans tp JOIN class_groups cg ON cg.id=tp.class_group_id AND cg.tenant_id=tp.tenant_id JOIN curriculum_components cc ON cc.id=tp.component_id AND cc.tenant_id=tp.tenant_id LEFT JOIN academic_periods ap ON ap.id=tp.academic_period_id AND ap.tenant_id=tp.tenant_id WHERE tp.tenant_id=? ORDER BY cg.name,cc.name,tp.updated_at DESC""",(tid,))
    raise DomainError("REPORT_NOT_IMPLEMENTED","Relatório não implementado.",422)


def _allowed(user: CurrentUser, code: str):
    item=definition(code)
    if not item: raise DomainError("REPORT_NOT_FOUND","Relatório não localizado.",404)
    if not item.roles.intersection(set(user.roles)): raise DomainError("FORBIDDEN","Sem permissão para este relatório.",403)
    return item


@router.get("/reports/catalog", operation_id="list_reports_catalog")
def list_catalog(user: CurrentUser = Depends(current_user)):
    return {"items": public_catalog(set(user.roles))}


@router.get("/reports/runs", operation_id="list_report_runs")
def list_runs(request: Request, user: CurrentUser = Depends(current_user)):
    tid=tenant(user); rows=request.state.store.fetch_all("SELECT * FROM report_runs WHERE tenant_id=? AND requested_by=? ORDER BY requested_at DESC LIMIT 200",(tid,user.id))
    for row in rows: row["parameters"]=json.loads(row.pop("parameters_json") or "{}")
    return {"items":rows}


@router.post("/reports/runs", status_code=201, operation_id="run_report")
def run_report(data: ReportRunInput, request: Request, user: CurrentUser = Depends(current_user)):
    tid=tenant(user); item=_allowed(user,data.report_code)
    if data.format not in item.formats: raise DomainError("REPORT_FORMAT_NOT_ALLOWED","Formato não permitido para este relatório.",422)
    missing=[name for name in item.required_parameters if data.parameters.get(name) in {None,""}]
    if missing: raise DomainError("REPORT_PARAMETERS_REQUIRED","Parâmetros obrigatórios ausentes.",422,errors=[{"field":name,"code":"REQUIRED","message":"Parâmetro obrigatório."} for name in missing])
    run_id=uuid7(); now=iso_now()
    request.state.store.execute("INSERT INTO report_runs(id,tenant_id,report_code,format,parameters_json,state,requested_by,requested_at,started_at) VALUES(?,?,?,?,?,?,?,?,?)",(run_id,tid,item.code,data.format,json.dumps(data.parameters,ensure_ascii=False,sort_keys=True),"running",user.id,now,now))
    try:
        rows=_rows(request,tid,item.code,data.parameters); columns=list(item.columns)
        if data.format=="pdf": content=render_pdf(title=item.title,subtitle=f"Gerado em {now} · {len(rows)} registro(s)",columns=columns,rows=rows); mime="application/pdf"; ext="pdf"
        elif data.format=="xlsx": content=render_xlsx(title=item.title,columns=columns,rows=rows); mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"; ext="xlsx"
        else: content=render_csv(columns=columns,rows=rows); mime="text/csv; charset=utf-8"; ext="csv"
        digest=hashlib.sha256(content).hexdigest(); key=f"reports/{item.code}/{run_id}.{ext}"; stored=request.app.state.data_router.object_storage(tid).put_bytes(key,content,content_type=mime)
        if stored.sha256!=digest: raise DomainError("REPORT_STORAGE_INTEGRITY_FAILED","Falha de integridade ao armazenar o relatório.",500)
        artifact_id=uuid7(); finished=iso_now(); filename=f"{item.code}-{run_id}.{ext}"
        with request.state.store.transaction() as conn:
            conn.execute("INSERT INTO report_artifacts(id,tenant_id,report_run_id,filename,mime_type,bytes,sha256,storage_key,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(artifact_id,tid,run_id,filename,mime,len(content),digest,key,finished))
            conn.execute("UPDATE report_runs SET state='completed',rows_count=?,finished_at=? WHERE tenant_id=? AND id=?",(len(rows),finished,tid,run_id))
            add_audit(conn,tenant_id=tid,actor_id=user.id,action="generate",aggregate_type="report_run",aggregate_id=run_id,correlation_id=request.state.correlation_id,after={"report_code":item.code,"format":data.format,"rows_count":len(rows),"sha256":digest})
            add_outbox(conn,tenant_id=tid,event_type="ReportGenerated",aggregate_type="report_run",aggregate_id=run_id,payload={"report_code":item.code,"format":data.format,"rows_count":len(rows),"artifact_id":artifact_id,"sha256":digest},correlation_id=request.state.correlation_id)
        return {"id":run_id,"report_code":item.code,"format":data.format,"state":"completed","rows_count":len(rows),"artifact":{"id":artifact_id,"filename":filename,"bytes":len(content),"sha256":digest,"mime_type":mime}}
    except DomainError:
        request.state.store.execute("UPDATE report_runs SET state='failed',finished_at=? WHERE tenant_id=? AND id=?",(iso_now(),tid,run_id)); raise
    except Exception as exc:
        request.state.store.execute("UPDATE report_runs SET state='failed',error_code='REPORT_GENERATION_FAILED',error_message=?,finished_at=? WHERE tenant_id=? AND id=?",(str(exc)[:500],iso_now(),tid,run_id)); raise DomainError("REPORT_GENERATION_FAILED","Falha ao gerar o relatório.",500) from exc


@router.get("/reports/runs/{run_id}", operation_id="get_report_run")
def get_run(run_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    tid=tenant(user); row=request.state.store.fetch_one("SELECT * FROM report_runs WHERE tenant_id=? AND id=?",(tid,run_id))
    if not row: raise DomainError("REPORT_RUN_NOT_FOUND","Execução de relatório não localizada.",404)
    _allowed(user,row["report_code"])
    row["parameters"]=json.loads(row.pop("parameters_json") or "{}")
    row["artifacts"]=request.state.store.fetch_all("SELECT id,filename,mime_type,bytes,sha256,created_at FROM report_artifacts WHERE tenant_id=? AND report_run_id=? ORDER BY created_at",(tid,run_id))
    return row


@router.get("/reports/runs/{run_id}/download", operation_id="download_report_run")
def download_run(run_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    tid=tenant(user); run=request.state.store.fetch_one("SELECT * FROM report_runs WHERE tenant_id=? AND id=? AND state='completed'",(tid,run_id))
    if not run: raise DomainError("REPORT_RUN_NOT_FOUND","Relatório concluído não localizado.",404)
    _allowed(user,run["report_code"]); artifact=request.state.store.fetch_one("SELECT * FROM report_artifacts WHERE tenant_id=? AND report_run_id=? ORDER BY created_at DESC LIMIT 1",(tid,run_id))
    if not artifact: raise DomainError("REPORT_ARTIFACT_NOT_FOUND","Artifact do relatório não localizado.",404)
    content=request.app.state.data_router.object_storage(tid).get_bytes(artifact["storage_key"])
    if hashlib.sha256(content).hexdigest()!=artifact["sha256"]: raise DomainError("REPORT_ARTIFACT_INTEGRITY_FAILED","Integridade do relatório inválida.",409)
    return Response(content=content,media_type=artifact["mime_type"],headers={"Content-Disposition":f'attachment; filename="{artifact["filename"]}"',"X-Content-SHA256":artifact["sha256"],"Cache-Control":"private, no-store"})
