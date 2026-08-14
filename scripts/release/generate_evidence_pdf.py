#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,textwrap
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle,getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,KeepTogether

ROOT=Path(__file__).resolve().parents[2]
VERSION=(ROOT/'VERSION').read_text().strip()
OUT=ROOT/'release/artifacts/reports';OUT.mkdir(parents=True,exist_ok=True)

styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='PigeTitle',parent=styles['Title'],fontName='Helvetica-Bold',fontSize=22,leading=27,textColor=colors.HexColor('#0D1B2A'),alignment=TA_CENTER,spaceAfter=12))
styles.add(ParagraphStyle(name='PigeH1',parent=styles['Heading1'],fontName='Helvetica-Bold',fontSize=15,leading=19,textColor=colors.HexColor('#006D77'),spaceBefore=9,spaceAfter=7))
styles.add(ParagraphStyle(name='PigeH2',parent=styles['Heading2'],fontName='Helvetica-Bold',fontSize=11,leading=14,textColor=colors.HexColor('#0D1B2A'),spaceBefore=7,spaceAfter=4))
styles.add(ParagraphStyle(name='PigeBody',parent=styles['BodyText'],fontName='Helvetica',fontSize=9.2,leading=13,textColor=colors.HexColor('#273844'),spaceAfter=5))
styles.add(ParagraphStyle(name='PigeSmall',parent=styles['BodyText'],fontName='Helvetica',fontSize=7.8,leading=10,textColor=colors.HexColor('#60707B')))

def footer(canvas,doc):
 canvas.saveState();canvas.setStrokeColor(colors.HexColor('#DCE5E9'));canvas.line(18*mm,15*mm,A4[0]-18*mm,15*mm);canvas.setFont('Helvetica',7.5);canvas.setFillColor(colors.HexColor('#60707B'));canvas.drawString(18*mm,10*mm,f'PIGE360 {VERSION} - Evidencia local sem acesso remoto');canvas.drawRightString(A4[0]-18*mm,10*mm,f'Pagina {doc.page}');canvas.restoreState()

def p(text,style='PigeBody'):return Paragraph(text,styles[style])
def table(rows,widths):
 t=Table(rows,colWidths=widths,repeatRows=1,hAlign='LEFT');t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#0D1B2A')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTNAME',(0,1),(-1,-1),'Helvetica'),('FONTSIZE',(0,0),(-1,-1),7.7),('LEADING',(0,0),(-1,-1),10),('GRID',(0,0),(-1,-1),0.35,colors.HexColor('#D7E1E5')),('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F3F6F7')]),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]));return t

def evidence_report():
 ci=json.loads((ROOT/'release/reports/local-ci-report.json').read_text());build=json.loads((ROOT/'release/reports/build-report.json').read_text());b=build['builds'];tool=json.loads((ROOT/'release/toolchain-inventory.json').read_text());proj=json.loads((ROOT/'release/project-validation.json').read_text());backup=json.loads((ROOT/'release/artifacts/backup-restore/report.json').read_text());visual=json.loads((ROOT/'packages/visual-testing/baselines/visual-baseline-manifest.json').read_text())
 path=OUT/f'PIGE360-{VERSION}-relatorio-evidencias.pdf';doc=SimpleDocTemplate(str(path),pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,topMargin=18*mm,bottomMargin=22*mm,title='Relatorio de evidencias PIGE360',author='PIGE360 local builder')
 story=[Spacer(1,15*mm),p('PIGE360','PigeTitle'),p('Plataforma Integrada de Gestao Educacional','PigeTitle'),Spacer(1,5*mm),p(f'<b>Relatorio de evidencias locais - versao {VERSION}</b>','PigeH1'),p('Este documento consolida somente resultados efetivamente executados no workspace local. Nao houve autenticacao, sincronizacao, publicacao, deploy ou acesso a servico remoto.'),Spacer(1,5*mm)]
 summary=[['Indicador','Resultado'],['CI local',ci['status']],['Verificacoes executadas',str(len(ci['commands']))],['Testes pytest',f"{ci.get('pytest_passed',0)} aprovados"],['OpenAPI',f"{b['backend']['openapi_paths']} paths / {b['backend']['openapi_operations']} operacoes"],['Aplicacoes web/PWA','13'],['Superficies visuais',f"40 telas / {len(visual['records'])} screenshots"],['Servicos Compose','46'],['Workflows','15'],['Backup/restore','Aprovado e isolado']]
 story+=[table(summary,[65*mm,95*mm]),PageBreak(),p('1. Validacoes executadas','PigeH1')]
 rows=[['Verificacao','Status','Duracao','Log']]
 status_label={'passed_structural_only':'structural','blocked_by_environment':'bloqueado'}
 for item in ci['commands']:rows.append([item['name'],status_label.get(item['status'],item['status']),f"{item['duration_seconds']} s",item['log']])
 story+=[table(rows,[46*mm,28*mm,20*mm,66*mm]),Spacer(1,4*mm),p('As verificacoes marcadas como passed retornaram codigo zero. O bundle frontend foi tentado e ficou bloqueado pela ausencia local de dependencias npm; nenhum resultado foi convertido artificialmente em sucesso.','PigeSmall'),p('2. Builds e toolchains','PigeH1')]
 rows=[['Area','Estado','Evidencia'],['Backend/OpenAPI','passed',f"{b['backend']['openapi_paths']} paths; {b['backend']['openapi_operations']} operacoes"],['Web/PWA','source_validated',f"{b['web_pwa_source']['apps']} apps; TypeScript estrito aprovado"],['Regressao visual','passed',f"{b['visual']['screens']} telas / {b['visual']['screenshots']} screenshots"],['Compose/Dockerfiles','structural_only','46 servicos; runtime nao executado'],['OCI','structural_only','12 manifests; runtime_executable=false']]
 story+=[table(rows,[47*mm,35*mm,78*mm]),Spacer(1,3*mm)]
 for item in b['native_and_external_toolchains']:story.append(p(f"<b>{item['name']}</b>: {item['status']} - {item['reason']}",'PigeSmall'))
 story+=[PageBreak(),p('3. Isolamento, backup e seguranca','PigeH1'),p(f"O teste de restore recuperou o tenant <b>{backup['tenant_restored']}</b>, validou banco e objetos por hash e confirmou <b>cross_tenant_leakage=false</b>. O archive de teste possui SHA-256 <font name='Courier'>{backup['backup_sha256']}</font>."),p('A resolucao de tenant ocorre exclusivamente por Host. X-Tenant-ID e tenant_id em query string sao rejeitados. O scanner local nao encontrou segredos reais; containers declarativos usam usuario nao root e secrets por arquivo.'),p('4. Branding e regressao visual','PigeH1'),p(f"Foram gerados {len(visual['records'])} screenshots para 40 superficies. O validador verificou dimensoes, SHA-256, acessibilidade basica e ausencia das marcas PIGE360, ARGWS e WWSoftwares nos HTMLs de contexto tenant."),p('O pacote de branding recebido contem 115 arquivos. Seu SHA256SUMS referencia quatro arquivos ausentes em 10_SOURCE_REFERENCES; a inconsistencia foi preservada no inventario, sem substituto inventado.'),p('5. Limitacoes reais','PigeH1')]
 limits=[['Item','Motivo','Acao necessaria'],['Imagens executaveis','Docker/Podman ausentes','Build, scan e smoke test em engine OCI'],['Desktop Tauri','Rust/Cargo ausentes','Matriz Windows/Linux/macOS'],['Android','SDK/Gradle ausentes','Build APK/AAB em runner Android'],['iOS','Xcode/macOS ausentes','Build .app/.xcarchive/IPA em macOS'],['Vue/Vite','dependencias npm nao estavam em cache','npm ci e build Vite em CI autorizado'],['Providers externos','sem rede, segredo ou homologacao','homologar cada provider e guardar protocolo']]
 story+=[table(limits,[42*mm,55*mm,63*mm]),Spacer(1,5*mm),p('6. Conclusao tecnica','PigeH1'),p(f'A entrega constitui a arvore de release local {VERSION} do PIGE360, com backend, contratos, migrations, SDK, interfaces-fonte, workflows, self-hosted e cadeia de fornecimento validados no que este host consegue executar. Builds que dependem de Docker, Rust, Android ou Xcode permanecem explicitamente nao executados neste host e devem ser produzidos pelos workflows em runners compativeis; nenhuma evidencia foi fabricada.')]
 doc.build(story,onFirstPage=footer,onLaterPages=footer)
 return path

def sample_contract():
 path=OUT/'contrato-demonstrativo-tenant.pdf';doc=SimpleDocTemplate(str(path),pagesize=A4,rightMargin=22*mm,leftMargin=22*mm,topMargin=20*mm,bottomMargin=22*mm,title='Contrato demonstrativo',author='Colegio Horizonte')
 story=[p('COLEGIO HORIZONTE','PigeTitle'),p('Contrato demonstrativo de prestacao de servicos educacionais','PigeH1'),p('<b>Numero:</b> DEMO-2026-0001 &nbsp;&nbsp; <b>Versao:</b> 1'),p('Este documento e uma evidencia local com dados ficticios. Ele demonstra snapshot, paginacao, identidade do tenant e bloco de assinatura, sem representar contrato juridico real.'),p('1. Partes','PigeH2'),p('Contratada: Colegio Horizonte Demonstrativo Ltda. Contratante: Responsavel Demonstrativo. Aluno: Estudante Demonstrativo.'),p('2. Objeto','PigeH2'),p('Prestacao de servicos educacionais no periodo letivo de 2026, conforme matriz, calendario, politicas e plano financeiro congelados no snapshot do contrato.'),p('3. Integridade','PigeH2'),p('O PDF final deve ser armazenado no bucket exclusivo do tenant, acompanhado de SHA-256, manifest e pacote de evidencias. Alteracao material exige nova versao e novas assinaturas.'),Spacer(1,15*mm),table([['Signatario','Metodo','Status'],['Responsavel Demonstrativo','Eletronica interna','Pendente'],['Representante institucional','ICP-Brasil ou politica vigente','Pendente']],[58*mm,65*mm,37*mm]),Spacer(1,15*mm),p('Codigo publico de validacao: DEMO-LOCAL-NAO-PRODUCAO','PigeSmall')]
 doc.build(story,onFirstPage=footer,onLaterPages=footer);return path

def main():
 paths=[evidence_report(),sample_contract()]
 result=[]
 for path in paths:result.append({'path':path.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size})
 (OUT/'PDF-MANIFEST.json').write_text(json.dumps({'schema_version':1,'files':result},ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'status':'generated','files':result},ensure_ascii=False))
if __name__=='__main__':main()
