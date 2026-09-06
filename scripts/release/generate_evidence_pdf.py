#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from evidence_common import collect_evidence, collect_inputs, project_root, read_json


def _styles() -> Any:
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="PigeTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=27,
            textColor=colors.HexColor("#0D1B2A"),
            alignment=TA_CENTER,
            spaceAfter=12,
        )
    )
    styles.add(
        ParagraphStyle(
            name="PigeH1",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=19,
            textColor=colors.HexColor("#006D77"),
            spaceBefore=9,
            spaceAfter=7,
        )
    )
    styles.add(
        ParagraphStyle(
            name="PigeH2",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#0D1B2A"),
            spaceBefore=7,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="PigeBody",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9.2,
            leading=13,
            textColor=colors.HexColor("#273844"),
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="PigeSmall",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=7.8,
            leading=10,
            textColor=colors.HexColor("#60707B"),
        )
    )
    return styles


STYLES = _styles()


def p(text: str, style: str = "PigeBody") -> Paragraph:
    return Paragraph(text, STYLES[style])


def table(rows: list[list[Any]], widths: list[float]) -> Table:
    converted = [[cell if isinstance(cell, Paragraph) else p(html.escape(str(cell)), "PigeSmall") for cell in row] for row in rows]
    result = Table(converted, colWidths=widths, repeatRows=1, hAlign="LEFT")
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0D1B2A")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D7E1E5")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F6F7")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return result


def _footer(version: str):
    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#DCE5E9"))
        canvas.line(18 * mm, 15 * mm, A4[0] - 18 * mm, 15 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#60707B"))
        canvas.drawString(18 * mm, 10 * mm, f"PIGE360 {version} - evidencias com escopo declarado")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Pagina {doc.page}")
        canvas.restoreState()

    return footer


def _network_text(network: dict[str, Any]) -> str:
    if network["network_used"] is True:
        return "Uso de rede registrado pelos relatorios desta execucao. Isso nao implica deploy, publicacao ou homologacao externa."
    if network["network_used"] is False:
        return "Os relatorios consultados registram que nao houve uso de rede nesta execucao."
    return "Os relatorios consultados nao registram se houve uso de rede; o manifesto preserva esse estado como desconhecido."


def _status(value: Any) -> str:
    return "nao informado" if value is None else str(value)


def write_operational_markdown(root: Path, evidence: dict[str, Any], inputs: dict[str, Any]) -> None:
    requirements = evidence["requirements"]
    status_rows = "\n".join(
        f"| {name} | {count} |" for name, count in requirements["status_summary"].items()
    )
    before_after = read_json(root / "docs/operations/BEFORE_AFTER_REPORT.json", required=False)
    before_summary = before_after.get("summary", {})
    compatibility = evidence["tree"]["source_compatibility"]
    final = f"""# Validacao local final - PIGE360 {evidence['version']}

Este documento separa tres classes de evidencia. Um resultado local ou estrutural nao e promovido a homologacao externa.

## Testes executados localmente

- Status da CI local: **{evidence['ci']['status']}**.
- Verificacoes registradas: **{evidence['ci']['checks_count']}**.
- Pytest: **{_status(evidence['tests']['pytest_passed'])} aprovados**, conforme `release/reports/test-report.json`.
- Frontend de producao: **{evidence['ci']['frontend_build_status']}**, conforme o comando `frontend-build` do relatorio local.
- OpenAPI: **{evidence['openapi']['paths']} paths, {evidence['openapi']['operations']} operacoes e {evidence['openapi']['schemas']} schemas**.
- Aplicacoes descobertas na arvore: **{evidence['tree']['applications']['count']}**.

## Validacoes estruturais

- Compose principal: **{evidence['tree']['compose']['services_count']} servicos declarados**; isto nao prova que os containers iniciam.
- OCI: **{evidence['oci']['images_count']} descritores**, status `{evidence['oci']['status']}`, `runtime_executable={str(evidence['oci']['runtime_executable']).lower()}`.
- Visual: **{evidence['visual']['screens']} superficies e {evidence['visual']['screenshots']} registros de baseline**; regressao pixel-a-pixel executada: **{str(evidence['visual']['pixel_regression_executed']).lower()}**.
- Workflows descobertos na arvore: **{evidence['tree']['workflows']['count']}**.

## Teste sintetico de backup/restore

O resultado `{evidence['backup_restore']['status']}` cobre tenants sinteticos em SQLite e filesystem local. Ele nao homologa restore de PostgreSQL nem de MinIO (`postgresql_restore_homologated=false`, `minio_restore_homologated=false`).

## Homologacao externa

Nao foi inferida de testes locais. Docker/Podman, PostgreSQL/Redis/RabbitMQ/MinIO reais, DNS/TLS, CloudPanel/Dockge, providers externos, lojas, assinatura e binarios nativos exigem seus ambientes e protocolos proprios.

## Ledger V8 recalculado

Foram recontados **{requirements['requirements_count']}** registros diretamente de `requirements`, sem confiar no resumo em cache.

| Estado | Quantidade |
|---|---:|
{status_rows}

Cache do ledger consistente com os registros: **{str(requirements['cache_matches_records']).lower()}**.

## Preservacao da base

- Arquivos removidos: **{_status(before_summary.get('removed'))}**.
- `*.vue.js`: **{compatibility['vue_js_count']}** presentes.
- `apps/*/src/main.js`: **{compatibility['main_js_count']}** presentes.
- Relatorio rastreavel: `docs/operations/BEFORE_AFTER_REPORT.json`.

## Rede e origem

{_network_text(evidence['network'])}

A revisao `{inputs['source_revision']['value']}` foi lida do comentario do ZIP-base e nao e apresentada como checkout Git verificado.
"""
    (root / "docs/operations/FINAL_LOCAL_VALIDATION.md").write_text(final, encoding="utf-8")

    commands = evidence["ci"]["commands"]
    command_rows = "\n".join(
        f"| `{item.get('name')}` | **{item.get('status')}** | {item.get('duration_seconds', 0)} s | `{item.get('log')}` |"
        for item in commands
    )
    sources = "\n".join(
        f"- `{item['source']}`: `network_used={str(item['network_used']).lower()}`"
        for item in evidence["network"]["sources"]
    ) or "- nenhum relatorio com o campo `network_used`"
    execution = f"""# Relatorio de execucao local

## Fontes de verdade

- Comandos e retornos: `release/reports/local-ci-report.json`.
- Testes pytest: `release/reports/test-report.json`.
- Builds e limitacoes: `release/reports/build-report.json`.
- Arvore original versus atual: `docs/operations/BEFORE_AFTER_REPORT.json`.
- Origem do ZIP-base: `docs/operations/SOURCE_BASELINE.json`.

## Resultado

| Verificacao | Status | Duracao | Evidencia |
|---|---|---:|---|
{command_rows}

## Uso de rede

{_network_text(evidence['network'])}

Relatorios consultados:

{sources}

## Limites de interpretacao

- `passed`: comando local executado com retorno zero.
- `structural_only`: arquivo, manifesto ou contrato validado sem executar o runtime alvo.
- baseline visual: catalogo e integridade dos screenshots; nao significa comparacao pixel-a-pixel.
- backup sintetico: SQLite/filesystem isolados; nao significa restore homologado de PostgreSQL/MinIO.
- homologacao externa: somente com ambiente, credenciais e protocolo reais.
"""
    (root / "docs/operations/LOCAL_EXECUTION_REPORT.md").write_text(execution, encoding="utf-8")


def evidence_report(root: Path, output_dir: Path, evidence: dict[str, Any], inputs: dict[str, Any]) -> Path:
    version = evidence["version"]
    path = output_dir / f"PIGE360-{version}-relatorio-evidencias.pdf"
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=22 * mm,
        title="Relatorio de evidencias PIGE360",
        author="PIGE360 release tooling",
    )
    tree = evidence["tree"]
    requirements = evidence["requirements"]
    before_after = read_json(root / "docs/operations/BEFORE_AFTER_REPORT.json", required=False)
    story = [
        Spacer(1, 15 * mm),
        p("PIGE360", "PigeTitle"),
        p("Plataforma Integrada de Gestao Educacional", "PigeTitle"),
        Spacer(1, 5 * mm),
        p(f"<b>Relatorio de evidencias - versao {html.escape(version)}</b>", "PigeH1"),
        p(
            "Este documento distingue teste local, validacao estrutural e homologacao externa. "
            "Nenhuma dessas classes e usada como substituta de outra."
        ),
        p(_network_text(evidence["network"])),
        Spacer(1, 5 * mm),
    ]
    summary = [
        ["Indicador", "Resultado", "Classe"],
        ["CI", evidence["ci"]["status"], "teste local"],
        ["Verificacoes", evidence["ci"]["checks_count"], "teste local"],
        ["Pytest", f"{_status(evidence['tests']['pytest_passed'])} aprovados", "teste local"],
        ["OpenAPI", f"{evidence['openapi']['paths']} paths / {evidence['openapi']['operations']} operacoes", "teste local"],
        ["Aplicacoes", tree["applications"]["count"], "inventario da arvore"],
        ["Workflows", tree["workflows"]["count"], "inventario da arvore"],
        ["Compose", f"{tree['compose']['services_count']} servicos", "estrutural"],
        ["Visual", f"{evidence['visual']['screens']} telas / {evidence['visual']['screenshots']} baselines", "baseline, nao pixel diff"],
        ["OCI", f"{evidence['oci']['images_count']} descritores; executavel={evidence['oci']['runtime_executable']}", "estrutural"],
    ]
    story.extend([table(summary, [49 * mm, 61 * mm, 50 * mm]), PageBreak(), p("1. Comandos locais", "PigeH1")])
    rows = [["Verificacao", "Status", "Duracao", "Log"]]
    for item in evidence["ci"]["commands"]:
        rows.append(
            [
                item.get("name"),
                item.get("status"),
                f"{item.get('duration_seconds', 0)} s",
                item.get("log"),
            ]
        )
    story.extend([table(rows, [44 * mm, 27 * mm, 20 * mm, 69 * mm]), Spacer(1, 4 * mm)])
    story.extend(
        [
            p("2. Escopo estrutural", "PigeH1"),
            p(
                f"O Compose principal declara {tree['compose']['services_count']} servicos. "
                "A contagem vem de compose.yaml; nao e evidencia de inicializacao dos containers."
            ),
            p(
                f"O artefato OCI possui {evidence['oci']['images_count']} descritores e status "
                f"{evidence['oci']['status']}. runtime_build_executed={evidence['oci']['runtime_build_executed']} "
                f"e runtime_executable={evidence['oci']['runtime_executable']}."
            ),
            p(
                f"O catalogo visual contem {evidence['visual']['screens']} superficies e "
                f"{evidence['visual']['screenshots']} screenshots. A comparacao pixel-a-pixel foi executada: "
                f"{evidence['visual']['pixel_regression_executed']}."
            ),
            p("3. Backup/restore", "PigeH1"),
            p(
                "O teste restaura tenants sinteticos em SQLite e arquivos locais, confere hashes e isolamento. "
                "Ele nao homologa PostgreSQL nem MinIO e nao substitui restore no ambiente de destino."
            ),
            p("4. Ledger V8", "PigeH1"),
            p(
                f"Foram recontados {requirements['requirements_count']} registros diretamente da lista do ledger. "
                f"O resumo em cache coincide com os registros: {requirements['cache_matches_records']}."
            ),
        ]
    )
    req_rows = [["Estado", "Quantidade"]] + [[name, count] for name, count in requirements["status_summary"].items()]
    story.extend([table(req_rows, [100 * mm, 35 * mm]), p("5. Origem e preservacao", "PigeH1")])
    canonical = inputs["source_baseline"].get("canonical_base", {})
    story.append(
        p(
            f"Base: {html.escape(str(canonical.get('name')))}; SHA-256 registrado: "
            f"<font name='Courier'>{html.escape(str(canonical.get('sha256')))}</font>. "
            f"A revisao {html.escape(str(inputs['source_revision']['value']))} vem do comentario do ZIP, sem checkout Git verificado."
        )
    )
    if before_after:
        before = before_after.get("summary", {})
        compatibility = before_after.get("source_compatibility", {})
        story.append(
            p(
                f"Antes/depois: adicionados={before.get('added')}, modificados={before.get('modified')}, "
                f"removidos={before.get('removed')}, inalterados={before.get('unchanged')}. "
                f"Preservacao *.vue.js={compatibility.get('vue_js', {}).get('current_count')} e "
                f"main.js={compatibility.get('main_js', {}).get('current_count')}."
            )
        )
    story.extend([p("6. Homologacao externa", "PigeH1")])
    native = evidence["builds"].get("native_and_external_toolchains", [])
    if isinstance(native, list):
        for item in native:
            story.append(
                p(
                    f"<b>{html.escape(str(item.get('name')))}</b>: {html.escape(str(item.get('status')))} - "
                    f"{html.escape(str(item.get('reason')))}",
                    "PigeSmall",
                )
            )
    story.append(
        p(
            "DNS/TLS, servidores, containers executaveis, bancos e object storage reais, providers, lojas, "
            "assinatura e binarios nativos permanecem dependentes de seus ambientes. A ausencia dessas provas "
            "nao e convertida em aprovacao."
        )
    )
    footer = _footer(version)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path


def sample_contract(root: Path, output_dir: Path, version: str) -> Path:
    path = output_dir / "contrato-demonstrativo-tenant.pdf"
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=22 * mm,
        leftMargin=22 * mm,
        topMargin=20 * mm,
        bottomMargin=22 * mm,
        title="Contrato demonstrativo",
        author="Colegio Horizonte",
    )
    story = [
        p("COLEGIO HORIZONTE", "PigeTitle"),
        p("Contrato demonstrativo de prestacao de servicos educacionais", "PigeH1"),
        p("<b>Numero:</b> DEMO-2026-0001 &nbsp;&nbsp; <b>Versao:</b> 1"),
        p("Este documento usa dados ficticios e nao representa contrato juridico real."),
        p("1. Partes", "PigeH2"),
        p("Contratada: Colegio Horizonte Demonstrativo Ltda. Contratante e aluno: dados demonstrativos."),
        p("2. Objeto", "PigeH2"),
        p("Prestacao demonstrativa de servicos educacionais no periodo letivo de 2026."),
        p("3. Integridade", "PigeH2"),
        p("O PDF final deve ser armazenado no escopo do tenant, com SHA-256 e pacote de evidencias."),
        Spacer(1, 15 * mm),
        table(
            [
                ["Signatario", "Metodo", "Status"],
                ["Responsavel Demonstrativo", "Eletronica interna", "Pendente"],
                ["Representante institucional", "Politica vigente", "Pendente"],
            ],
            [58 * mm, 65 * mm, 37 * mm],
        ),
        Spacer(1, 15 * mm),
        p("Codigo publico de validacao: DEMO-LOCAL-NAO-PRODUCAO", "PigeSmall"),
    ]
    footer = _footer(version)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", help="raiz alternativa; tambem aceita PIGE360_PROJECT_ROOT")
    parser.add_argument("--output-dir", default="release/artifacts/reports")
    parser.add_argument("--input", action="append", default=[])
    args = parser.parse_args()
    root = project_root(args.root)
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence = collect_evidence(root)
    inputs = collect_inputs(root, args.input)
    write_operational_markdown(root, evidence, inputs)
    paths = [
        evidence_report(root, output_dir, evidence, inputs),
        sample_contract(root, output_dir, evidence["version"]),
    ]
    result = [
        {
            "path": path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }
        for path in paths
    ]
    (output_dir / "PDF-MANIFEST.json").write_text(
        json.dumps({"schema_version": 2, "files": result}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "generated", "files": result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
