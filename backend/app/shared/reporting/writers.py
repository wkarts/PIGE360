from __future__ import annotations

import csv
import io
import zipfile
from html import escape
from typing import Any, Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Sim" if value else "Não"
    return str(value)


def render_csv(*, columns: list[tuple[str, str]], rows: Iterable[dict[str, Any]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([label for _, label in columns])
    for row in rows:
        writer.writerow([_text(row.get(key)) for key, _ in columns])
    return output.getvalue().encode("utf-8-sig")


def _xlsx_col(index: int) -> str:
    result = ""
    while index:
        index, rem = divmod(index - 1, 26)
        result = chr(65 + rem) + result
    return result


def render_xlsx(*, title: str, columns: list[tuple[str, str]], rows: list[dict[str, Any]]) -> bytes:
    """Gera XLSX OOXML determinístico sem arquivo temporário ou callback global."""
    sheet_rows: list[str] = []
    values = [[label for _, label in columns], *[[_text(row.get(key)) for key, _ in columns] for row in rows]]
    for r_idx, values_row in enumerate(values, 1):
        cells: list[str] = []
        for c_idx, value in enumerate(values_row, 1):
            ref = f"{_xlsx_col(c_idx)}{r_idx}"
            style = ' s="1"' if r_idx == 1 else ""
            cells.append(f'<c r="{ref}" t="inlineStr"{style}><is><t xml:space="preserve">{escape(value)}</t></is></c>')
        sheet_rows.append(f'<row r="{r_idx}">{"".join(cells)}</row>')
    last_col = _xlsx_col(max(1, len(columns)))
    sheet = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:{last_col}{max(1,len(values))}"/><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><sheetFormatPr defaultRowHeight="15"/><sheetData>{''.join(sheet_rows)}</sheetData><autoFilter ref="A1:{last_col}{max(1,len(values))}"/></worksheet>'''
    workbook = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{escape(title[:31] or 'Relatório')}" sheetId="1" r:id="rId1"/></sheets></workbook>'''
    styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs></styleSheet>'''
    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>'''
    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'''
    workbook_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name, payload in [
            ("[Content_Types].xml", content_types), ("_rels/.rels", root_rels),
            ("xl/workbook.xml", workbook), ("xl/_rels/workbook.xml.rels", workbook_rels),
            ("xl/styles.xml", styles), ("xl/worksheets/sheet1.xml", sheet),
        ]:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, payload.encode("utf-8"))
    return out.getvalue()


def render_pdf(*, title: str, subtitle: str, columns: list[tuple[str, str]], rows: list[dict[str, Any]]) -> bytes:
    output = io.BytesIO(); styles = getSampleStyleSheet()
    page = landscape(A4) if len(columns) > 5 else A4
    doc = SimpleDocTemplate(output, pagesize=page, leftMargin=12*mm, rightMargin=12*mm, topMargin=12*mm, bottomMargin=12*mm, title=title, author="PIGE360")
    story = [Paragraph(escape(title), styles["Title"]), Paragraph(escape(subtitle), styles["Normal"]), Spacer(1, 6*mm)]
    table_data: list[list[Any]] = [[Paragraph(escape(label), styles["BodyText"]) for _, label in columns]]
    for row in rows:
        table_data.append([Paragraph(escape(_text(row.get(key)))[:2000], styles["BodyText"]) for key, _ in columns])
    if not rows:
        table_data.append([Paragraph("Nenhum registro encontrado.", styles["BodyText"]), *["" for _ in columns[1:]]])
    usable = page[0] - 24*mm
    col_width = usable / max(1, len(columns))
    table = Table(table_data, repeatRows=1, colWidths=[col_width] * len(columns), hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#F2F4F7")), ("TEXTCOLOR", (0,0), (-1,0), colors.HexColor("#0D1B2A")),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTNAME", (0,1), (-1,-1), "Helvetica"),
        ("FONTSIZE", (0,0), (-1,-1), 7.5 if len(columns)>5 else 9), ("GRID", (0,0), (-1,-1), 0.25, colors.HexColor("#D0D5DD")),
        ("VALIGN", (0,0), (-1,-1), "TOP"), ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#FAFAFA")]),
        ("LEFTPADDING", (0,0), (-1,-1), 4), ("RIGHTPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(table); doc.build(story)
    return output.getvalue()
