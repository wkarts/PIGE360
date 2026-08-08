#!/usr/bin/env python3
from __future__ import annotations

import json
import keyword
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "docs" / "api" / "openapi.json"
OUT = ROOT / "packages" / "api-sdk" / "src" / "generated"


def safe(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_$]", "_", name)
    if not value or value[0].isdigit() or keyword.iskeyword(value):
        value = f"_{value}"
    return value


def ts_type(schema: dict[str, Any] | None) -> str:
    if not schema:
        return "unknown"
    if "$ref" in schema:
        return safe(schema["$ref"].rsplit("/", 1)[-1])
    if "const" in schema:
        return json.dumps(schema["const"], ensure_ascii=False)
    if "enum" in schema:
        return " | ".join(json.dumps(x, ensure_ascii=False) for x in schema["enum"]) or "never"
    if "anyOf" in schema:
        return " | ".join(dict.fromkeys(ts_type(x) for x in schema["anyOf"]))
    if "oneOf" in schema:
        return " | ".join(dict.fromkeys(ts_type(x) for x in schema["oneOf"]))
    typ = schema.get("type")
    if isinstance(typ, list):
        return " | ".join(ts_type({**schema, "type": x}) for x in typ)
    if typ == "string":
        return "string"
    if typ in {"integer", "number"}:
        return "number"
    if typ == "boolean":
        return "boolean"
    if typ == "null":
        return "null"
    if typ == "array":
        return f"Array<{ts_type(schema.get('items'))}>"
    if typ == "object" or "properties" in schema or "additionalProperties" in schema:
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        members = [f"{json.dumps(k, ensure_ascii=False)}{'?' if k not in required else ''}: {ts_type(v)}" for k, v in props.items()]
        additional = schema.get("additionalProperties")
        if additional is True:
            members.append("[key: string]: unknown")
        elif isinstance(additional, dict):
            members.append(f"[key: string]: {ts_type(additional)}")
        return "{ " + "; ".join(members) + " }"
    return "unknown"


def operation_response(operation: dict[str, Any]) -> str:
    responses = operation.get("responses", {})
    for code in sorted(responses):
        if not str(code).startswith("2"):
            continue
        content = responses[code].get("content", {})
        if "application/json" in content:
            return ts_type(content["application/json"].get("schema"))
    return "unknown"


def main() -> None:
    spec = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    schemas = spec.get("components", {}).get("schemas", {})
    type_lines = ["/* Gerado de docs/api/openapi.json. Não editar manualmente. */", ""]
    for name, schema in sorted(schemas.items()):
        type_lines.append(f"export type {safe(name)} = {ts_type(schema)};")
    (OUT / "types.ts").write_text("\n".join(type_lines) + "\n", encoding="utf-8")

    operations = []
    methods = []
    for path, path_item in sorted(spec["paths"].items()):
        for method, operation in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            op_id = safe(operation["operationId"])
            params = operation.get("parameters", [])
            path_params = [p for p in params if p.get("in") == "path"]
            query_params = [p for p in params if p.get("in") == "query"]
            header_params = [p for p in params if p.get("in") == "header"]
            request_body = operation.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
            input_members = []
            for p in path_params:
                input_members.append(f"{safe(p['name'])}{'' if p.get('required') else '?'}: {ts_type(p.get('schema'))}")
            if query_params:
                q_members = [f"{safe(p['name'])}{'' if p.get('required') else '?'}: {ts_type(p.get('schema'))}" for p in query_params]
                input_members.append("query?: { " + "; ".join(q_members) + " }")
            if header_params:
                h_members = [f"{json.dumps(p['name'])}{'' if p.get('required') else '?'}: {ts_type(p.get('schema'))}" for p in header_params]
                input_members.append("headers?: { " + "; ".join(h_members) + " }")
            if request_body:
                input_members.append(f"body: {ts_type(request_body)}")
            input_type = "{ " + "; ".join(input_members) + " }" if input_members else "void"
            output_type = operation_response(operation)
            operations.append({"operationId": operation["operationId"], "method": method.upper(), "path": path, "tags": operation.get("tags", [])})
            arg = "input: " + input_type if input_type != "void" else "input?: void"
            methods.append(f"  {op_id}({arg}, options?: RequestOptions): Promise<{output_type}> {{ return this.request({json.dumps(method.upper())}, {json.dumps(path)}, input as RequestInput, options); }}")

    imports = ", ".join(safe(name) for name in sorted(schemas))
    client = '''/* Gerado de docs/api/openapi.json. Não editar manualmente. */
import type { __IMPORTS__ } from "./types";

export type RequestOptions = { signal?: AbortSignal; idempotencyKey?: string; correlationId?: string; headers?: Record<string,string> };
type RequestInput = { query?: Record<string, unknown>; headers?: Record<string, unknown>; body?: unknown; [key: string]: unknown } | void;
export type ApiClientOptions = { baseUrl: string; getAccessToken?: () => string | undefined; fetchImpl?: typeof fetch };

export class Pige360ApiClient {
  readonly #baseUrl: string;
  readonly #getAccessToken: (() => string | undefined) | undefined;
  readonly #fetch: typeof fetch;
  constructor(options: ApiClientOptions) { this.#baseUrl=options.baseUrl.replace(/\\/$/,""); this.#getAccessToken=options.getAccessToken; this.#fetch=options.fetchImpl ?? fetch; }
  private async request<T>(method:string,pathTemplate:string,input:RequestInput,options?:RequestOptions):Promise<T>{
    const source=(input ?? {}) as Record<string,unknown>; let path=pathTemplate;
    for(const match of pathTemplate.matchAll(/\\{([^}]+)\\}/g)){ const key=match[1]; if(!key)continue; const value=source[key]; if(value===undefined) throw new Error(`Parâmetro de rota ausente: ${key}`); path=path.replace(match[0],encodeURIComponent(String(value))); }
    const url=new URL(this.#baseUrl+path); const query=source.query as Record<string,unknown>|undefined;
    if(query) for(const [key,value] of Object.entries(query)){ if(value===undefined||value===null)continue; if(Array.isArray(value)) for(const item of value)url.searchParams.append(key,String(item)); else url.searchParams.set(key,String(value)); }
    const headers=new Headers(options?.headers); headers.set("Accept","application/json"); const token=this.#getAccessToken?.(); if(token)headers.set("Authorization",`Bearer ${token}`); if(options?.idempotencyKey)headers.set("Idempotency-Key",options.idempotencyKey); if(options?.correlationId)headers.set("X-Correlation-ID",options.correlationId);
    const inputHeaders=source.headers as Record<string,unknown>|undefined; if(inputHeaders) for(const [key,value] of Object.entries(inputHeaders)) if(value!==undefined) headers.set(key,String(value));
    let body:BodyInit|undefined; if(source.body!==undefined){headers.set("Content-Type","application/json");body=JSON.stringify(source.body);}
    const init:RequestInit={method,headers}; if(body!==undefined)init.body=body; if(options?.signal)init.signal=options.signal;
    const response=await this.#fetch(url,init); const contentType=response.headers.get("content-type")??"";
    if(!response.ok){const detail=contentType.includes("json")?await response.json():await response.text();const error=new Error(`PIGE360 API ${response.status}`) as Error&{status:number;problem:unknown};error.status=response.status;error.problem=detail;throw error;}
    if(response.status===204)return undefined as T; return (contentType.includes("json")?await response.json():await response.text()) as T;
  }
'''.replace("__IMPORTS__", imports)
    client += "\n".join(methods) + "\n}\n"
    (OUT / "client.ts").write_text(client, encoding="utf-8")
    (OUT / "operations.json").write_text(json.dumps(operations, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "packages" / "api-sdk" / "src" / "index.ts").write_text('export * from "./generated/types";\nexport * from "./generated/client";\n', encoding="utf-8")
    (ROOT / "packages" / "api-sdk" / "package.json").write_text(json.dumps({"name":"@pige360/api-sdk","version":spec["info"]["version"],"private":True,"type":"module","exports":{".":"./src/index.ts"}}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"schemas": len(schemas), "operations": len(operations), "output": str(OUT.relative_to(ROOT))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
