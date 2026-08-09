from __future__ import annotations


def test_openapi_has_unique_operation_ids_and_required_domains(local_env):
    response = local_env.client.get("/api/v1/openapi.json", headers={"host": "api.platform.local"})
    assert response.status_code == 200
    schema = response.json()
    operation_ids = []
    for path_item in schema["paths"].values():
        for method, operation in path_item.items():
            if method.lower() in {"get", "post", "put", "patch", "delete", "options", "head"}:
                operation_ids.append(operation["operationId"])
    assert len(operation_ids) == len(set(operation_ids))
    assert len(schema["paths"]) >= 150
    required = {
        "/api/v1/teaching-plans",
        "/api/v1/class-sessions/{session_id}/attendance",
        "/api/v1/platform/tenants/{tenant_id}/branding",
        "/api/v1/platform/tenants/{tenant_id}/apps/builds",
        "/api/v1/contracts/{contract_id}/generate",
    }
    assert required.issubset(schema["paths"])
