from __future__ import annotations

import hashlib
import io
import zipfile


def _create_product(env):
    product=env.client.post("/api/v1/products",headers=env.alpha_headers(),json={"sku":"REPORT-001","barcode":"7890000000999","name":"Livro de Relatório","product_type":"book","ncm":"49019900","unit":"UN","cost":"20.00","sale_price":"35.00"})
    assert product.status_code==201,product.text
    adjusted=env.client.post(f"/api/v1/products/{product.json()['id']}/stock-adjustments",headers={**env.alpha_headers(),"Idempotency-Key":"report-stock-001"},json={"quantity":"7","warehouse":"default","reason":"Carga para relatório","unit_cost":"20.00"})
    assert adjusted.status_code==200,adjusted.text
    return product.json()


def test_reporting_catalog_generates_xlsx_pdf_with_integrity_and_tenant_isolation(local_env):
    _create_product(local_env)
    catalog=local_env.client.get("/api/v1/reports/catalog",headers=local_env.alpha_headers())
    assert catalog.status_code==200,catalog.text
    assert "inventory_stock" in {x["code"] for x in catalog.json()["items"]}

    xlsx=local_env.client.post("/api/v1/reports/runs",headers=local_env.alpha_headers(),json={"report_code":"inventory_stock","format":"xlsx","parameters":{}})
    assert xlsx.status_code==201,xlsx.text
    assert xlsx.json()["rows_count"]==1
    xlsx_download=local_env.client.get(f"/api/v1/reports/runs/{xlsx.json()['id']}/download",headers=local_env.alpha_headers())
    assert xlsx_download.status_code==200
    assert xlsx_download.content.startswith(b"PK")
    assert hashlib.sha256(xlsx_download.content).hexdigest()==xlsx_download.headers["x-content-sha256"]
    with zipfile.ZipFile(io.BytesIO(xlsx_download.content)) as zf:
        assert "xl/worksheets/sheet1.xml" in zf.namelist()
        sheet=zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        assert "Livro de Relatório" in sheet and "REPORT-001" in sheet

    pdf=local_env.client.post("/api/v1/reports/runs",headers=local_env.alpha_headers(),json={"report_code":"inventory_stock","format":"pdf","parameters":{}})
    assert pdf.status_code==201,pdf.text
    pdf_download=local_env.client.get(f"/api/v1/reports/runs/{pdf.json()['id']}/download",headers=local_env.alpha_headers())
    assert pdf_download.status_code==200 and pdf_download.content.startswith(b"%PDF-")
    assert hashlib.sha256(pdf_download.content).hexdigest()==pdf_download.headers["x-content-sha256"]

    beta_runs=local_env.client.get("/api/v1/reports/runs",headers=local_env.beta_headers())
    assert beta_runs.status_code==200 and beta_runs.json()["items"]==[]
    cross=local_env.client.get(f"/api/v1/reports/runs/{xlsx.json()['id']}",headers=local_env.beta_headers())
    assert cross.status_code==404


def test_reporting_permissions_and_required_parameters(local_env):
    teacher,token=local_env.create_alpha_user("report-teacher@alpha.example.com",["teacher"])
    headers=local_env.headers("admin.alpha.school.local",token)
    catalog=local_env.client.get("/api/v1/reports/catalog",headers=headers)
    assert catalog.status_code==200 and catalog.json()["items"]==[]
    denied=local_env.client.post("/api/v1/reports/runs",headers=headers,json={"report_code":"finance_receivables","format":"pdf","parameters":{}})
    assert denied.status_code==403
    missing=local_env.client.post("/api/v1/reports/runs",headers=local_env.alpha_headers(),json={"report_code":"payroll_run","format":"pdf","parameters":{}})
    assert missing.status_code==422 and missing.json()["code"]=="REPORT_PARAMETERS_REQUIRED"
