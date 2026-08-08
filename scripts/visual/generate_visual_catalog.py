#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs" / "design"
CATALOG = DOCS / "screen-catalog"
SCREENS_DIR = CATALOG / "screens"
PREVIEWS = DOCS / "generated-previews"
BASELINES = ROOT / "packages" / "visual-testing" / "baselines"
PLATFORM_SVG = ROOT / "packages" / "tenant-branding" / "brands" / "platform-pige360" / "01_LOGOS" / "SVG" / "pige360-symbol.svg"
TENANT_SVG = ROOT / "packages" / "tenant-branding" / "brands" / "demo-horizonte" / "logo-symbol.svg"
SOURCE_INVENTORY = ROOT.parent / "evidence" / "initial" / "branding-assets-inventory.json"


@dataclass(frozen=True)
class Screen:
    number: int
    slug: str
    app: str
    context: str
    title: str
    subtitle: str
    module: str
    metrics: tuple[tuple[str, str, str], ...]
    table_headers: tuple[str, ...]
    table_rows: tuple[tuple[str, ...], ...]
    actions: tuple[str, ...]
    mobile: bool = False
    wide: bool = False


SCREENS = [
    Screen(1,"control-plane-dashboard","platform-console","platform","Console global","Tenants, licenças e provisionamento sob uma visão operacional única.","Control Plane",(("Tenants ativos","128","+4 neste mês"),("SLO global","99,97%","janela de 30 dias"),("Alertas","3","1 crítico")),("Tenant","Plano","Saúde","Última atividade"),(('Rede Municipal Aurora','Enterprise','Operacional','há 2 min'),('Colégio Vértice','Dedicated','Operacional','há 5 min'),('Instituto Caminhos','SaaS','Atenção','há 11 min')),("Novo tenant","Abrir incidentes","Exportar relatório"),wide=True),
    Screen(2,"tenant-admin-dashboard","tenant-admin-web","tenant","Painel administrativo","Indicadores acadêmicos, financeiros e operacionais da instituição.","Visão da escola",(("Alunos ativos","1.842","98,4% rematriculados"),("Frequência hoje","94,8%","42 chamadas pendentes"),("Recebimento","R$ 684 mil","92% da competência")),("Área","Indicador","Status","Responsável"),(('Secretaria','17 matrículas pendentes','Atenção','Equipe de matrícula'),('Pedagógico','8 planos para aprovar','Pendente','Coordenação'),('Financeiro','36 títulos vencidos','Monitorado','Tesouraria')),("Nova matrícula","Publicar aviso","Gerar relatório"),wide=True),
    Screen(3,"public-school-portal","public-portal","tenant","Portal institucional","Informação pública, matrículas, calendário e canais de atendimento.","Portal público",(("Vagas abertas","64","Educação infantil e fundamental"),("Próximo evento","12 ago","Feira de Ciências"),("Atendimento","08h–18h","segunda a sexta")),("Serviço","Disponibilidade","Canal","Prazo"),(('Pré-matrícula','Aberta','Online','até 30/08'),('Declarações','Disponível','Protocolo digital','2 dias úteis'),('Calendário letivo','Atualizado','Consulta pública','imediato')),("Fazer pré-matrícula","Consultar protocolo","Ver calendário"),mobile=True),
    Screen(4,"family-mobile-home","family-app","tenant","Olá, família Oliveira","Acompanhe a rotina escolar de Arthur e Luísa com segurança.","Família",(("Frequência","96,2%","acima da meta"),("Próxima parcela","12 ago","R$ 742,00"),("Saldo cantina","R$ 86,40","limite semanal ativo")),("Hoje","Aluno","Atividade","Situação"),(('07:30','Arthur','Entrada registrada','Confirmado'),('09:20','Luísa','Atividade de leitura','Concluída'),('12:10','Arthur','Almoço','Autorizado')),("Justificar falta","Pagar parcela","Enviar mensagem"),mobile=True),
    Screen(5,"family-finance-and-canteen","family-app","tenant","Financeiro e cantina","Controle de parcelas, pagamentos e consumo dos dependentes.","Família · Financeiro",(("Em aberto","R$ 742,00","vence em 12/08"),("Pago no ano","R$ 5.936,00","8 comprovantes"),("Carteiras","R$ 143,20","2 dependentes")),("Descrição","Competência","Valor","Situação"),(('Mensalidade','08/2026','R$ 742,00','Em aberto'),('Material didático','08/2026','R$ 94,00','Pago'),('Recarga cantina','07/08/2026','R$ 60,00','Confirmada')),("Pagar com PIX","Ver extrato","Definir limite"),mobile=True),
    Screen(6,"teacher-mobile-diary","teacher-app","tenant","Diário do professor","Aulas, conteúdo ministrado, avaliações e pendências da semana.","Professor · Diário",(("Aulas hoje","5","4 registradas"),("Planos aprovados","18","2 em revisão"),("Pendências","3","antes do fechamento")),("Horário","Turma","Componente","Diário"),(('07:30','7º A','Matemática','Concluído'),('09:20','8º B','Matemática','Rascunho'),('11:10','7º C','Projeto Integrador','Pendente')),("Iniciar aula","Registrar conteúdo","Sincronizar"),mobile=True),
    Screen(7,"teacher-attendance-offline","teacher-app","tenant","Chamada offline","Lista disponível no dispositivo, com outbox e resolução explícita de conflitos.","Professor · Frequência",(("Alunos","31","matrícula validada"),("Presentes","28","2 faltas · 1 atraso"),("Sincronização","Pendente","3 eventos na outbox")),("Aluno","Situação","Horário","Observação"),(('Ana Clara','Presente','07:31','—'),('Bruno Lima','Falta','—','Aguardando justificativa'),('Carla Souza','Atraso','07:48','Tolerância excedida')),("Marcar todos presentes","Salvar rascunho","Enviar chamada"),mobile=True),
    Screen(8,"student-mobile-home","student-app","tenant","Minha escola","Agenda, tarefas, notas, frequência e biblioteca em um só lugar.","Aluno",(("Tarefas","4","2 para amanhã"),("Média geral","8,4","+0,3 no bimestre"),("Frequência","95,6%","situação regular")),("Data","Atividade","Componente","Status"),(('08/08','Lista de exercícios','Matemática','Em andamento'),('09/08','Resenha','Língua Portuguesa','Não iniciada'),('12/08','Feira de Ciências','Projeto Integrador','Confirmado')),("Abrir tarefa","Ver boletim","Renovar livro"),mobile=True),
    Screen(9,"admin-mobile-dashboard","admin-app","tenant","Gestão no celular","Aprovações, alertas e indicadores essenciais para decisões rápidas.","Administrativo mobile",(("Aprovações","12","4 urgentes"),("Inadimplência","4,8%","dentro da meta"),("Chamadas","91%","18 pendentes")),("Prioridade","Processo","Área","Prazo"),(('Alta','Reabertura de diário','Pedagógico','hoje'),('Média','Desconto excepcional','Financeiro','amanhã'),('Baixa','Compra de material','Compras','12/08')),("Aprovar","Delegar","Abrir painel"),mobile=True),
    Screen(10,"pos-canteen-sale","pos-app","tenant","Venda na cantina","Operação rápida com identificação do aluno, restrições e saldo em tempo real.","PDV · Cantina",(("Caixa","Aberto","desde 06:45"),("Carrinho","R$ 18,50","3 itens"),("Carteira","R$ 42,80","limite permitido")),("Item","Qtd.","Unitário","Total"),(('Suco natural','1','R$ 6,00','R$ 6,00'),('Sanduíche integral','1','R$ 9,50','R$ 9,50'),('Fruta','1','R$ 3,00','R$ 3,00')),("Identificar aluno","Finalizar venda","Suspender pedido"),mobile=True),
    Screen(11,"pos-products-and-nfce","pos-app","tenant","Produtos e NFC-e","Catálogo, tributação, estoque e emissão vinculados à venda.","PDV · Fiscal",(("Produtos ativos","286","14 com estoque baixo"),("NFC-e autorizadas","174","100% hoje"),("Contingência","Desativada","SEFAZ operacional")),("Produto","NCM","Estoque","Fiscal"),(('Caderno 10 matérias','48202000','28','Pronto'),('Camisa uniforme M','61091000','11','Pronto'),('Kit de pintura','96082000','7','Revisar cClassTrib')),("Novo produto","Sincronizar catálogo","Consultar NFC-e"),wide=True),
    Screen(12,"kiosk-self-service","kiosk-app","tenant","Autoatendimento","Consulta, protocolo, pagamentos e retirada com fluxo restrito.","Kiosk",(("Serviços","8","disponíveis"),("Fila atual","6 min","estimativa"),("Terminal","Online","sincronizado")),("Opção","Descrição","Autenticação","Tempo"),(('2ª via de boleto','Gerar ou pagar','CPF + data','2 min'),('Protocolo','Acompanhar solicitação','Código','1 min'),('Retirada autorizada','Confirmar responsável','QR Code','1 min')),("Iniciar atendimento","Ler QR Code","Chamar suporte"),mobile=True),
    Screen(13,"timeclock-terminal","timeclock-app","tenant","Registro de ponto","Terminal restrito com identificação, offline seguro e auditoria.","Controle de ponto",(("Horário","08:14:32","sexta-feira"),("Status","Online","última sincronização agora"),("Registros hoje","126","0 divergências")),("Colaborador","Evento","Horário","Origem"),(('Marina Costa','Entrada','08:02','NFC'),('Rafael Alves','Entrada','08:07','QR Code'),('Bianca Dias','Intervalo','08:12','Cartão')),("Registrar ponto","Usar QR Code","Consultar recibo"),mobile=True),
    Screen(14,"academic-secretary","tenant-admin-web","tenant","Secretaria acadêmica","Matrículas, documentos, vagas e movimentações com trilha completa.","Secretaria",(("Matrículas ativas","1.842","ano letivo 2026"),("Pré-matrículas","73","17 aguardando documento"),("Protocolos","28","SLA médio 1,4 dia")),("Aluno","Processo","Turma","Status"),(('Amanda Ribeiro','Rematrícula','8º A','Em análise'),('João Miguel','Transferência','6º B','Documentação'),('Luiza Rocha','Matrícula','Infantil 5','Aprovada')),("Nova matrícula","Emitir declaração","Importar documentos"),wide=True),
    Screen(15,"enrollment-workflow","tenant-admin-web","tenant","Fluxo de matrícula","Etapas, documentos, contrato, financeiro e ativação coordenados.","Matrícula",(("Em andamento","37","9 vencendo hoje"),("Conversão","82%","últimos 30 dias"),("Tempo médio","2,1 dias","meta 3 dias")),("Etapa","Responsável","Pendências","Situação"),(('Dados do aluno','Secretaria','0','Concluída'),('Documentos','Responsável','2','Pendente'),('Contrato e assinatura','Financeiro','1','Em andamento'),('Enturmação','Coordenação','0','Aguardando')),("Validar documentos","Gerar contrato","Ativar matrícula"),wide=True),
    Screen(16,"pedagogical-dashboard","tenant-admin-web","tenant","Painel pedagógico","Cobertura curricular, planos, diários, avaliações e risco escolar.","Pedagógico",(("Cobertura curricular","78%","meta mensal 80%"),("Planos pendentes","8","3 devolvidos"),("Alunos em risco","24","acompanhamento ativo")),("Turma","Planejado","Ministrado","Risco"),(('7º A','82%','79%','Baixo'),('8º B','77%','68%','Moderado'),('9º A','84%','81%','Baixo')),("Revisar planos","Abrir intervenções","Comparar períodos"),wide=True),
    Screen(17,"financial-dashboard","tenant-admin-web","tenant","Painel financeiro","Recebimentos, inadimplência, caixa e conciliação por competência.","Financeiro",(("Recebido","R$ 684 mil","92% da meta"),("Em aberto","R$ 59 mil","4,8% inadimplência"),("Conciliação","98,7%","12 pendências")),("Competência","Previsto","Recebido","Situação"),(('08/2026','R$ 742.400','R$ 684.120','Em curso'),('07/2026','R$ 735.900','R$ 724.330','Fechada'),('06/2026','R$ 728.100','R$ 718.840','Fechada')),("Gerar cobrança","Conciliar extrato","Exportar DRE"),wide=True),
    Screen(18,"fiscal-nfe-nfce-nfse","tenant-admin-web","tenant","Documentos fiscais","NF-e, NFC-e e NFS-e roteadas pela natureza da operação.","Fiscal",(("Autorizados hoje","184","0 rejeições finais"),("Em processamento","7","retry automático"),("Certificado A1","92 dias","alerta antecipado")),("Documento","Operação","Valor","Status"),(('NFC-e 004281','Cantina','R$ 18,50','Autorizada'),('NF-e 000944','Uniformes PJ','R$ 1.284,00','Autorizada'),('NFS-e 013820','Mensalidade 08/2026','R$ 742,00','Processando')),("Emitir documento","Reprocessar fila","Baixar XML"),wide=True),
    Screen(19,"tax-reform-ibs-cbs","tenant-admin-web","tenant","Reforma tributária IBS/CBS","Prontidão por estabelecimento, classificação e simulação versionada.","Fiscal · RTC",(("Prontidão","87%","+6 p.p. no mês"),("Sem cClassTrib","42","itens para revisar"),("Ruleset","2026.08.1","vigente desde 01/08")),("Cadastro","Pendência","Impacto","Ação"),(('Produtos','17 sem CST IBS/CBS','Médio','Classificar'),('Serviços','9 sem NBS','Alto','Revisar'),('Regras','3 vencem em 30 dias','Médio','Versionar')),("Executar simulação","Revisar catálogo","Gerar relatório"),wide=True),
    Screen(20,"contracts-and-signatures","tenant-admin-web","tenant","Contratos e assinaturas","Modelos versionados, envelopes, evidências e cadeia de custódia.","Contratos",(("Aguardando assinatura","38","12 vencem em 48h"),("Assinados no mês","412","98,2% concluídos"),("Validações","100%","hash e evidências íntegros")),("Contrato","Partes","Método","Status"),(('Matrícula 2026-01842','3','Eletrônica interna','Parcialmente assinado'),('Transporte 2026-00411','2','ICP-Brasil','Assinado'),('Rematrícula 2026-01902','3','Eletrônica interna','Aguardando')),("Novo modelo","Enviar lembrete","Validar documento"),wide=True),
    Screen(21,"govbr-signature-flow","tenant-admin-web","tenant","Assinatura GOV.BR","Provider condicional, homologação controlada e fallback documentado.","Assinaturas",(("Provider","Não configurado","credenciais ausentes"),("Elegibilidade","Pendente","tenant privado"),("Fallback","Disponível","ICP-Brasil e assinatura interna")),("Etapa","Verificação","Resultado","Observação"),(('Elegibilidade institucional','Contrato/tenant','Não elegível','Provider permanece inativo'),('OAuth 2.0','Credenciais','Não executado','Sem segredos locais'),('Assinatura PKCS#7','Homologação','Não executado','Fixture contratual disponível')),("Testar configuração","Ver documentação","Usar outro método"),wide=True),
    Screen(22,"mailcow-inbox","tenant-admin-web","tenant","E-mail institucional","Caixa integrada por IMAPS/SMTP, com conteúdo oficial preservado no provedor.","Comunicação · E-mail",(("Não lidas","14","3 prioritárias"),("Caixas ativas","126","quota 61%"),("Sincronização","Saudável","última há 1 min")),("Remetente","Assunto","Pasta","Recebido"),(('Coordenação','Reunião pedagógica','Entrada','08:01'),('Financeiro','Conciliação concluída','Entrada','07:48'),('Biblioteca','Inventário mensal','Projetos','ontem')),("Nova mensagem","Criar regra","Administrar caixas"),wide=True),
    Screen(23,"employee-and-hr","tenant-admin-web","tenant","Pessoas e RH","Admissão, documentos, desenvolvimento, benefícios e histórico funcional.","RH",(("Colaboradores","214","208 ativos"),("Admissões","7","em onboarding"),("Documentos","11","próximos do vencimento")),("Colaborador","Função","Lotação","Situação"),(('Camila Ferreira','Professora','Unidade Centro','Ativa'),('Diego Santos','Auxiliar administrativo','Unidade Norte','Onboarding'),('Renata Melo','Coordenadora','Unidade Centro','Férias programadas')),("Nova admissão","Programar férias","Abrir avaliações"),wide=True),
    Screen(24,"payroll","tenant-admin-web","tenant","Folha de pagamento","Competências, rubricas, bases, rateios e fechamento auditado.","Folha",(("Competência","07/2026","em conferência"),("Líquido","R$ 846 mil","214 colaboradores"),("Divergências","5","antes do fechamento")),("Rubrica","Base","Valor","Incidência"),(('Salário base','214','R$ 1.102.400','INSS/IRRF/FGTS'),('Horas extras','38','R$ 28.740','INSS/IRRF/FGTS'),('Vale transporte','96','R$ 14.380','Desconto')),("Processar simulação","Conferir divergências","Fechar competência"),wide=True),
    Screen(25,"timekeeping","tenant-admin-web","tenant","Controle de ponto","Jornadas, ocorrências, banco de horas e integração com folha.","Ponto",(("Marcações hoje","628","99,1% válidas"),("Pendências","17","9 aguardam gestor"),("Banco de horas","+384h","saldo consolidado")),("Colaborador","Ocorrência","Saldo","Status"),(('Paulo Mendes','Atraso 12 min','-0:12','Aguardando justificativa'),('Alice Nunes','Hora extra','+1:24','Aprovada'),('Joana Silva','Ausência','-8:00','Em análise')),("Importar AFD","Aprovar ajustes","Fechar período"),wide=True),
    Screen(26,"events-and-travel","tenant-admin-web","tenant","Eventos e viagens","Planejamento, autorizações, pagamentos, check-in e segurança.","Eventos",(("Próximos eventos","8","3 com viagem"),("Autorizações","86%","42 pendentes"),("Orçamento","R$ 92 mil","74% comprometido")),("Evento","Data","Participantes","Situação"),(('Feira de Ciências','12/08','480','Confirmado'),('Visita técnica','18/08','42','Autorizações'),('Jogos estudantis','24/08','128','Inscrições abertas')),("Novo evento","Cobrar autorização","Abrir check-in"),wide=True),
    Screen(27,"notices","tenant-admin-web","tenant","Avisos e comunicados","Publicação segmentada, confirmação de leitura e múltiplos canais.","Comunicação",(("Publicados","18","últimos 7 dias"),("Leitura média","91%","+3 p.p."),("Confirmações","326","42 pendentes")),("Aviso","Público","Canais","Leitura"),(('Reunião de responsáveis','7º e 8º anos','Push · E-mail','94%'),('Manutenção programada','Todos','App · Portal','89%'),('Campanha de vacinação','Infantil','WhatsApp · Push','87%')),("Novo aviso","Enviar lembrete","Ver analytics"),wide=True),
    Screen(28,"service-requests","tenant-admin-web","tenant","Solicitações e protocolos","Formulários versionados, SLA, aprovações e automações.","Atendimento",(("Em aberto","64","8 próximos do SLA"),("Tempo médio","1,4 dia","meta 2 dias"),("Satisfação","4,7/5","132 avaliações")),("Protocolo","Tipo","Responsável","Status"),(('2026-009812','Declaração escolar','Secretaria','Em produção'),('2026-009806','Revisão de nota','Coordenação','Em análise'),('2026-009799','Renegociação','Financeiro','Aguardando documentos')),("Abrir solicitação","Reatribuir fila","Configurar SLA"),wide=True),
    Screen(29,"inventory","tenant-admin-web","tenant","Estoque, compras e patrimônio","Movimentações, lotes, validade, requisições e ativos.","Suprimentos",(("Itens ativos","1.284","48 abaixo do mínimo"),("Pedidos abertos","17","R$ 82 mil"),("Patrimônio","3.942","96% inventariado")),("Item","Local","Saldo","Status"),(('Papel A4','Almoxarifado central','28 resmas','Baixo'),('Toner preto','Unidade Centro','12 un.','Regular'),('Projetor multimídia','Sala 18','1 ativo','Em manutenção')),("Nova requisição","Realizar inventário","Abrir cotação"),wide=True),
    Screen(30,"library","tenant-admin-web","tenant","Biblioteca","Acervo físico e digital, reservas, empréstimos e inventário.","Biblioteca",(("Títulos","8.412","12.906 exemplares"),("Empréstimos","634","42 vencidos"),("Reservas","76","prazo médio 2 dias")),("Título","Usuário","Devolução","Status"),(('O Pequeno Príncipe','Ana Clara','10/08','Em dia'),('Capitães da Areia','Bruno Lima','05/08','Atrasado'),('Matemática Essencial','Carla Souza','12/08','Em dia')),("Novo empréstimo","Importar acervo","Cobrar atrasos"),wide=True),
    Screen(31,"transportation","tenant-admin-web","tenant","Transporte escolar","Rotas, veículos, presença, ocorrências e comunicação com responsáveis.","Transporte",(("Rotas ativas","14","1 em desvio"),("Alunos transportados","486","98% confirmados"),("Veículos","18","16 em operação")),("Rota","Motorista","Ocupação","Status"),(('Rota Norte 02','Carlos Dias','86%','Em percurso'),('Rota Centro 01','Marta Luz','92%','Concluída'),('Rota Sul 03','Roberto Lima','74%','Atraso 8 min')),("Abrir mapa","Registrar ocorrência","Notificar famílias"),wide=True),
    Screen(32,"cloudflare-domain-provisioning","platform-console","platform","Provisionamento de domínios","DNS, custom hostnames, certificados e rotas reconciliados por estado.","Edge e domínios",(("Hosts ativos","1.126","99,9% saudáveis"),("Certificados","1.118","8 em emissão"),("Reconciliações","24","sem falha crítica")),("Hostname","Tenant","TLS","Status"),(('admin.colegiovertice.example','Colégio Vértice','Full strict','Ativo'),('familia.redeaurora.example','Rede Aurora','Full strict','Ativo'),('apps.institutocaminhos.example','Instituto Caminhos','Emitindo','Aguardando DNS')),("Provisionar hostname","Reconciliar","Ver certificados"),wide=True),
    Screen(33,"tenant-branding-studio","branding-studio","tenant","Estúdio de marca","Tokens, ativos e previews da escola com versionamento e rollback.","Branding",(("Versão ativa","v3","publicada em 05/08"),("Contraste","AA","todas as superfícies"),("Ativos","34","originais preservados")),("Superfície","Tema","Validação","Status"),(('Portal da família','Claro/Escuro','WCAG AA','Aprovado'),('PDF e documentos','Impressão','Hash e margem','Aprovado'),('Aplicativos','Android/iOS','Ícone e splash','Rebuild necessário')),("Nova versão","Comparar versões","Publicar"),wide=True),
    Screen(34,"tenant-app-factory","platform-console","platform","Fábrica de aplicativos","Manifestos por tenant, builds isolados e distribuição condicional.","App Factory",(("Builds na fila","9","3 plataformas"),("Concluídos hoje","21","18 assinados"),("Sem credencial","4","artefatos unsigned")),("Tenant/App","Plataforma","Brand version","Status"),(('Horizonte Família','Android','v3','Testando'),('Vértice Professor','iOS','v8','Aguardando assinatura'),('Aurora Desktop','Windows x64','v5','Disponível')),("Solicitar build","Reprocessar","Abrir artefatos"),wide=True),
    Screen(35,"tenant-download-center","tenant-download-center","tenant","Central de aplicativos","Downloads próprios da escola, hashes, canais e instruções por plataforma.","Downloads",(("Aplicativos","7","4 plataformas"),("Canal","Estável","beta opcional"),("Downloads no mês","1.482","auditados")),("Aplicativo","Plataforma","Versão","Integridade"),(('Horizonte Família','Android','1.6.2','SHA-256 verificado'),('Horizonte Professor','iOS','1.6.2','App Store'),('Horizonte Gestão','Windows x64','1.6.1','Assinado')),("Baixar aplicativo","Ver changelog","Escanear QR Code"),mobile=True),
    Screen(36,"platform-health-and-observability","platform-console","platform","Saúde e observabilidade","SLOs, traces, filas, bancos e integrações em uma visão correlacionada.","Operações",(("Disponibilidade","99,97%","30 dias"),("p95 API","184 ms","meta 250 ms"),("DLQ","7","3 domínios")),("Serviço","SLO","Latência","Status"),(('API tenant','99,98%','142 ms','Saudável'),('Workers fiscais','99,92%','2,4 s','Atenção'),('MinIO','100%','31 ms','Saudável')),("Abrir traces","Reprocessar DLQ","Criar incidente"),wide=True),
    Screen(37,"reports-and-print-preview","tenant-admin-web","tenant","Relatórios e impressão","PDF/XLSX com filtros tipados, preview real e identidade da escola.","Relatórios",(("Modelos","86","12 favoritos"),("Gerados hoje","214","100% com hash"),("Fila","3","tempo médio 18 s")),("Relatório","Formato","Período","Status"),(('Frequência por turma','PDF/XLSX','07/2026','Disponível'),('Planejado × ministrado','PDF/XLSX','2º bimestre','Disponível'),('Inadimplência','XLSX','08/2026','Processando')),("Gerar relatório","Abrir preview","Agendar envio"),wide=True),
    Screen(38,"desktop-admin","desktop-admin","tenant","Administração desktop","Operação integrada com impressão, cache local e atualização controlada.","Desktop",(("Sincronização","Online","checkpoint atual"),("Atualização","1.6.2","canal estável"),("Impressoras","3","2 disponíveis")),("Processo","Origem","Destino","Status"),(('Relatório de matrícula','API','Impressora Secretaria','Concluído'),('Etiquetas de patrimônio','Cache local','Térmica 01','Na fila'),('Recibos de cantina','API','PDF','Concluído')),("Nova impressão","Ver sincronização","Buscar atualização"),wide=True),
    Screen(39,"mobile-app-suite","admin-app","tenant","Suíte de aplicativos","Família, professor, aluno, gestão, PDV, kiosk e ponto sob políticas comuns.","Aplicativos",(("Apps habilitados","7","contrato ativo"),("Usuários móveis","2.814","86% ativos no mês"),("Versões suportadas","2","atualização gradual")),("Aplicativo","Usuários","Offline","Versão"),(('Família','1.742','Consultas e outbox','1.6.2'),('Professor','124','Chamada e diário','1.6.2'),('Aluno','948','Materiais e tarefas','1.6.1')),("Gerenciar apps","Ver adoção","Publicar aviso"),mobile=True),
    Screen(40,"full-product-architecture-board","platform-console","platform","Arquitetura integral do produto","Control Plane, Tenant Plane, clientes, eventos e dados com fronteiras explícitas.","Arquitetura",(("Domínios","47","monólito modular"),("Rotas API","328","OpenAPI versionada"),("Aplicações","13","web, PWA e Tauri")),("Camada","Responsabilidade","Fonte de verdade","Isolamento"),(('Control Plane','Tenants, domínios, licenças','PostgreSQL control','Global auditado'),('Tenant Plane','Domínios educacionais','Banco por tenant','Físico + RLS'),('Clientes','Web/mobile/desktop','SQLite offline + API','Tenant e usuário'),('Eventos','Outbox/inbox e filas','RabbitMQ + PostgreSQL','Contexto assinado')),("Abrir ADRs","Ver mapa de domínios","Exportar arquitetura"),wide=True),
]


def _svg_data(svg_path: Path) -> str:
    raw = svg_path.read_text(encoding="utf-8")
    # Direct inline SVG avoids any external network/resource dependency.
    return raw.replace("<svg ", '<svg class="brand-symbol" ')


def _screen_html(screen: Screen) -> str:
    platform = screen.context == "platform"
    brand_name = "PIGE360" if platform else "Colégio Horizonte"
    brand_subtitle = "Plataforma Integrada de Gestão Educacional" if platform else "Gestão educacional"
    brand_svg = _svg_data(PLATFORM_SVG if platform else TENANT_SVG)
    nav = (
        ["Visão global", "Tenants", "Infraestrutura", "Aplicativos", "Segurança", "Operações"]
        if platform else
        ["Visão geral", "Secretaria", "Pedagógico", "Financeiro", "Comunicação", "Configurações"]
    )
    nav_html = "".join(f'<button class="nav-item" aria-label="Abrir {html.escape(item)}"><span>{i+1:02d}</span>{html.escape(item)}</button>' for i,item in enumerate(nav))
    metrics_html = "".join(
        f'<article class="metric"><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong><small>{html.escape(detail)}</small><div class="spark"><i style="width:{64 + ((idx*11+screen.number)%31)}%"></i></div></article>'
        for idx,(label,value,detail) in enumerate(screen.metrics)
    )
    headers = "".join(f"<th>{html.escape(x)}</th>" for x in screen.table_headers)
    rows = "".join("<tr>" + "".join(f'<td><span class="cell-value">{html.escape(cell)}</span></td>' for cell in row) + "</tr>" for row in screen.table_rows)
    actions = "".join(f'<button class="action {"primary" if i==0 else ""}">{html.escape(action)}</button>' for i,action in enumerate(screen.actions))
    chart_bars = "".join(f'<i style="height:{34 + ((screen.number*13+i*17)%58)}%"><span>{i+1}</span></i>' for i in range(10))
    return f'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(screen.title)} — {html.escape(brand_name)}</title>
<style>
:root{{--deep:#0D1B2A;--petrol:#006D77;--teal:#14B8A6;--blue:#3B82F6;--orange:#F59E0B;--gold:#FFD166;--paper:#F2F4F7;--tenant:#174C4F;--tenant2:#2B7A78;--tenantAccent:#F4A261;--bg:#eef3f5;--panel:#fff;--text:#10212c;--muted:#60707b;--line:#dbe4e8;--shadow:0 18px 50px rgba(13,27,42,.09);--brand:{'#006D77' if platform else '#174C4F'};--brand2:{'#14B8A6' if platform else '#2B7A78'};--accent:{'#F59E0B' if platform else '#F4A261'};}}
*{{box-sizing:border-box}}html,body{{margin:0;min-height:100%;font-family:Inter,Arial,Helvetica,sans-serif;background:var(--bg);color:var(--text)}}
body[data-theme=dark]{{--bg:#09141d;--panel:#10212c;--text:#edf6f7;--muted:#9eb0b9;--line:#263c48;--shadow:0 18px 55px rgba(0,0,0,.35)}}
button,input{{font:inherit}}button{{cursor:pointer}}.app{{min-height:100vh;display:grid;grid-template-columns:248px 1fr}}.sidebar{{background:linear-gradient(165deg,var(--deep),#102d3b);color:#fff;padding:26px 18px;display:flex;flex-direction:column;gap:24px}}.brand{{display:flex;align-items:center;gap:12px;padding:3px 7px 18px;border-bottom:1px solid rgba(255,255,255,.14)}}.brand-symbol{{width:42px;height:42px;flex:none}}.brand-copy strong{{font-family:Poppins,Inter,sans-serif;display:block;font-size:17px;letter-spacing:.01em}}.brand-copy small{{display:block;color:#b8cbd3;font-size:10px;line-height:1.3;margin-top:3px}}.nav{{display:grid;gap:7px}}.nav-item{{border:0;background:transparent;color:#dce8eb;text-align:left;padding:11px 10px;border-radius:10px;display:flex;gap:10px;align-items:center}}.nav-item:first-child,.nav-item:hover{{background:rgba(255,255,255,.11);color:#fff}}.nav-item span{{font-size:9px;opacity:.65}}.sidebar-foot{{margin-top:auto;border-top:1px solid rgba(255,255,255,.14);padding-top:16px;font-size:11px;color:#b8cbd3;display:grid;gap:7px}}
.main{{min-width:0;padding:24px 28px 28px}}.topbar{{display:flex;justify-content:space-between;gap:18px;align-items:center;margin-bottom:22px}}.crumb{{font-size:11px;text-transform:uppercase;letter-spacing:.12em;color:var(--brand);font-weight:800}}h1{{font-family:Poppins,Inter,sans-serif;margin:5px 0 2px;font-size:27px;line-height:1.1}}.subtitle{{margin:0;color:var(--muted);font-size:13px;max-width:760px}}.top-actions{{display:flex;align-items:center;gap:10px}}.search{{width:230px;background:var(--panel);color:var(--text);border:1px solid var(--line);padding:11px 13px;border-radius:11px;outline:none}}.avatar{{width:40px;height:40px;border-radius:50%;display:grid;place-items:center;background:linear-gradient(135deg,var(--brand),var(--brand2));color:#fff;font-weight:800;border:3px solid var(--panel);box-shadow:var(--shadow)}}
.metrics{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:15px}}.metric,.panel,.side-card{{background:var(--panel);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow)}}.metric{{padding:16px 17px;position:relative;overflow:hidden}}.metric:after{{content:"";position:absolute;right:-18px;top:-24px;width:86px;height:86px;border-radius:50%;background:color-mix(in srgb,var(--brand) 10%,transparent)}}.metric span{{display:block;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.08em}}.metric strong{{display:block;font-size:25px;margin:6px 0 3px;font-family:Poppins,Inter,sans-serif}}.metric small{{color:var(--muted);font-size:11px}}.spark{{height:4px;background:var(--line);border-radius:99px;margin-top:13px;overflow:hidden}}.spark i{{display:block;height:100%;background:linear-gradient(90deg,var(--brand),var(--accent));border-radius:99px}}
.content{{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(260px,.7fr);gap:15px;margin-top:15px}}.panel{{padding:17px;min-width:0}}.panel-head{{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:13px}}h2{{font-family:Poppins,Inter,sans-serif;font-size:15px;margin:0}}.badge{{font-size:10px;background:color-mix(in srgb,var(--brand) 12%,transparent);color:var(--brand);padding:6px 9px;border-radius:999px;font-weight:800}}table{{width:100%;border-collapse:collapse;font-size:12px}}th{{text-align:left;color:var(--muted);font-size:9px;text-transform:uppercase;letter-spacing:.08em;padding:9px 8px;border-bottom:1px solid var(--line)}}td{{padding:12px 8px;border-bottom:1px solid var(--line);vertical-align:middle}}tr:last-child td{{border-bottom:0}}td:last-child .cell-value{{display:inline-flex;padding:5px 8px;border-radius:999px;background:color-mix(in srgb,var(--teal) 12%,transparent);color:var(--brand);font-weight:700}}.side-stack{{display:grid;gap:15px}}.side-card{{padding:16px}}.chart{{height:145px;display:flex;align-items:flex-end;gap:6px;padding-top:16px}}.chart i{{flex:1;min-width:5px;background:linear-gradient(180deg,var(--brand2),var(--brand));border-radius:5px 5px 2px 2px;position:relative;opacity:.9}}.chart i span{{position:absolute;bottom:-17px;left:50%;transform:translateX(-50%);font-size:8px;color:var(--muted)}}.progress-list{{display:grid;gap:13px;margin-top:14px}}.progress-row{{font-size:11px;color:var(--muted)}}.progress-row div{{height:6px;background:var(--line);border-radius:99px;margin-top:5px;overflow:hidden}}.progress-row i{{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,var(--brand),var(--accent))}}.actions{{display:flex;gap:9px;flex-wrap:wrap;margin-top:15px}}.action{{border:1px solid var(--line);background:var(--panel);color:var(--text);padding:10px 12px;border-radius:10px;font-size:11px;font-weight:750}}.action.primary{{border-color:var(--brand);background:var(--brand);color:#fff}}.offline-note{{position:fixed;right:18px;bottom:17px;background:var(--deep);color:#fff;padding:10px 13px;border-radius:12px;font-size:10px;box-shadow:var(--shadow);display:flex;align-items:center;gap:8px}}.offline-note i{{width:8px;height:8px;border-radius:50%;background:var(--teal)}}
@media(max-width:760px){{.app{{display:block}}.sidebar{{display:none}}.main{{padding:16px 13px 82px}}.topbar{{align-items:flex-start}}.top-actions .search{{display:none}}h1{{font-size:21px}}.subtitle{{font-size:11px;max-width:270px}}.metrics{{grid-template-columns:1fr 1fr;gap:9px}}.metric{{padding:13px}}.metric:last-child{{grid-column:1/-1}}.metric strong{{font-size:20px}}.content{{grid-template-columns:1fr;gap:10px;margin-top:10px}}.side-stack{{grid-template-columns:1fr 1fr;gap:10px}}.chart{{height:105px}}table{{font-size:10px}}th:nth-child(3),td:nth-child(3){{display:none}}.panel{{padding:13px}}.actions{{position:fixed;z-index:5;left:0;right:0;bottom:0;margin:0;padding:10px 12px;background:color-mix(in srgb,var(--panel) 94%,transparent);backdrop-filter:blur(8px);border-top:1px solid var(--line);flex-wrap:nowrap;overflow:auto}}.action{{white-space:nowrap;flex:1}}.offline-note{{right:12px;bottom:68px}}}}
</style></head>
<body data-theme="light" data-screen="{screen.slug}" data-context="{screen.context}"><div class="app">
<aside class="sidebar"><div class="brand">{brand_svg}<div class="brand-copy"><strong>{html.escape(brand_name)}</strong><small>{html.escape(brand_subtitle)}</small></div></div><nav class="nav">{nav_html}</nav><div class="sidebar-foot"><span>Ambiente local validado</span><span>v1.0.0</span></div></aside>
<main class="main"><header class="topbar"><div><div class="crumb">{html.escape(screen.module)}</div><h1>{html.escape(screen.title)}</h1><p class="subtitle">{html.escape(screen.subtitle)}</p></div><div class="top-actions"><input class="search" aria-label="Buscar" placeholder="Buscar nesta área"><div class="avatar" aria-label="Perfil">WK</div></div></header>
<section class="metrics">{metrics_html}</section><section class="content"><article class="panel"><div class="panel-head"><h2>Visão operacional</h2><span class="badge">Atualizado agora</span></div><table><thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table><div class="actions">{actions}</div></article><div class="side-stack"><article class="side-card"><div class="panel-head"><h2>Tendência</h2><span class="badge">30 dias</span></div><div class="chart">{chart_bars}</div></article><article class="side-card"><div class="panel-head"><h2>Qualidade</h2><span class="badge">Monitorado</span></div><div class="progress-list"><div class="progress-row">Integridade<div><i style="width:96%"></i></div></div><div class="progress-row">Conformidade<div><i style="width:88%"></i></div></div><div class="progress-row">Conclusão<div><i style="width:79%"></i></div></div></div></article></div></section></main></div>
<div class="offline-note"><i></i><span>Sincronização segura ativa</span></div>
<script>const q=new URLSearchParams(location.search);document.body.dataset.theme=q.get('theme')==='dark'?'dark':'light';</script></body></html>'''


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def generate_sources() -> None:
    SCREENS_DIR.mkdir(parents=True, exist_ok=True)
    for screen in SCREENS:
        (SCREENS_DIR / f"{screen.slug}.html").write_text(_screen_html(screen), encoding="utf-8")

    cards = []
    for s in SCREENS:
        rel = f"screens/{s.slug}.html"
        cards.append(f'<a class="card" href="{rel}"><b>{s.number:02d}</b><span>{html.escape(s.title)}</span><small>{html.escape(s.app)} · {html.escape(s.context)}</small></a>')
    index = f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Catálogo visual local</title><style>*{{box-sizing:border-box}}body{{font-family:Inter,Arial,sans-serif;margin:0;background:#eef3f5;color:#0D1B2A;padding:32px}}header{{max-width:1200px;margin:auto auto 24px}}h1{{margin:0 0 8px}}p{{color:#60707b}}main{{max-width:1200px;margin:auto;display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}}.card{{background:white;border:1px solid #dbe4e8;border-radius:14px;padding:18px;text-decoration:none;color:inherit;display:grid;gap:7px;box-shadow:0 12px 35px rgba(13,27,42,.06)}}.card b{{color:#006D77;font-size:12px}}.card span{{font-weight:800}}.card small{{color:#60707b}}</style></head><body><header><h1>Catálogo visual local</h1><p>40 superfícies implementadas para validação de layout, branding, responsividade e estados. Nenhum recurso externo é carregado.</p></header><main>{''.join(cards)}</main></body></html>'''
    (CATALOG / "index.html").write_text(index, encoding="utf-8")


def generate_reference_assets() -> None:
    reference_dir = DOCS / "reference-assets"
    reference_dir.mkdir(parents=True, exist_ok=True)
    source_data: Any = []
    if SOURCE_INVENTORY.is_file():
        source_data = json.loads(SOURCE_INVENTORY.read_text(encoding="utf-8"))
    items = source_data.get("files", source_data) if isinstance(source_data, dict) else source_data
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized.append({
            "path": item.get("path") or item.get("relative_path") or item.get("name"),
            "sha256": item.get("sha256"),
            "bytes": item.get("bytes") or item.get("size"),
            "media_type": item.get("media_type") or item.get("mime_type"),
            "source": "PIGE360_BRANDING_COMPLETO.zip",
        })
    manifest = {
        "schema_version": 1,
        "generated_locally": True,
        "source_archive_sha256": "9cc110eddc20c82b7176580f0aff09f16471cb0650d4ba32a2fe059f3d76f2ef",
        "assets_count": len(normalized),
        "known_source_integrity_issue": {
            "description": "O SHA256SUMS do pacote referencia quatro arquivos ausentes em 10_SOURCE_REFERENCES.",
            "missing": [f"10_SOURCE_REFERENCES/source-reference-{i:02d}.png" for i in range(1,5)],
        },
        "files": normalized,
    }
    (reference_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    map_dir = DOCS / "reference-map"
    map_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Mapa de referências visuais",
        "",
        "As referências canônicas são os ativos do pacote oficial de branding. Os originais são preservados; a interface consome tokens e providers, não caminhos hardcoded.",
        "",
        "| Nº | Arquivo/Origem | SHA-256 | Aplicação | Rota/Tela | Plataforma | Breakpoints | Componentes | Reprodução | Status | Screenshot |",
        "|---:|---|---|---|---|---|---|---|---|---|---|",
    ]
    # Map the main platform references to all screen groups and expose their hashes.
    refs = [
        ROOT / "packages/tenant-branding/brands/platform-pige360/07_PRESENTATION_BOARDS/pige360-brand-board-01.png",
        ROOT / "packages/tenant-branding/brands/platform-pige360/07_PRESENTATION_BOARDS/pige360-brand-board-02.png",
        ROOT / "packages/tenant-branding/brands/platform-pige360/08_RECONSTRUCTED_REFERENCES/reference-01-pige360.png",
        ROOT / "packages/tenant-branding/brands/platform-pige360/08_RECONSTRUCTED_REFERENCES/reference-02-pige360.png",
        ROOT / "packages/tenant-branding/brands/platform-pige360/08_RECONSTRUCTED_REFERENCES/reference-03-pige360.png",
        ROOT / "packages/tenant-branding/brands/platform-pige360/08_RECONSTRUCTED_REFERENCES/reference-04-pige360.png",
    ]
    for s in SCREENS:
        ref = refs[(s.number - 1) % len(refs)]
        ref_rel = ref.relative_to(ROOT).as_posix()
        expected = "símbolo, paleta, gradientes e linguagem" if s.context == "platform" else "estrutura e tokens; marca substituída pelo TenantBrandKit"
        screenshot = f"../generated-previews/{s.context}/{s.app}/{s.slug}/desktop-1366x768-light.png"
        lines.append(f"| {s.number:02d} | `{ref_rel}` | `{sha256(ref)}` | `{s.app}` | `{s.slug}` | web/PWA/desktop/mobile | 390×844, 1366×768, 1920×1080 quando aplicável | sidebar, titlebar, métricas, tabela, ações, estados | {expected} | implementado | [abrir]({screenshot}) |")
    lines.extend([
        "",
        "## Precedência aplicada",
        "",
        "1. Segurança, isolamento e integridade de dados.",
        "2. Comando V8 e adendo de branding.",
        "3. Pacote oficial PIGE360 para superfícies globais.",
        "4. `TenantBrandKit` do Colégio Horizonte para superfícies da escola.",
        "",
        "## Inconsistência preservada",
        "",
        "O manifesto interno `SHA256SUMS.txt` referencia quatro arquivos de `10_SOURCE_REFERENCES/` que não existem no ZIP recebido. Nenhum substituto foi inventado; as referências reconstruídas existentes em `08_RECONSTRUCTED_REFERENCES/` foram inventariadas normalmente.",
    ])
    (map_dir / "REFERENCE_MAP.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_previews(chromium: str) -> list[dict[str, Any]]:
    if PREVIEWS.exists():
        shutil.rmtree(PREVIEWS)
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    mobile_ids = {s.number for s in SCREENS if s.mobile}
    wide_ids = {s.number for s in SCREENS if s.wide}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=chromium, args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 1366, "height": 768}, device_scale_factor=1)
        for screen in SCREENS:
            target_dir = PREVIEWS / screen.context / screen.app / screen.slug
            target_dir.mkdir(parents=True, exist_ok=True)
            html_document = (SCREENS_DIR / f"{screen.slug}.html").read_text(encoding="utf-8")
            variants = [(1366,768,"light"),(1366,768,"dark")]
            if screen.number in mobile_ids:
                variants.extend([(390,844,"light"),(390,844,"dark")])
            if screen.number in wide_ids:
                variants.append((1920,1080,"light"))
            for width,height,theme in variants:
                page.set_viewport_size({"width":width,"height":height})
                page.set_content(html_document, wait_until="load")
                page.evaluate("theme => document.body.dataset.theme = theme", theme)
                page.emulate_media(color_scheme=theme)
                filename = ("mobile" if width < 600 else "desktop") + f"-{width}x{height}-{theme}.png"
                out = target_dir / filename
                page.screenshot(path=str(out), full_page=False)
                with Image.open(out) as image:
                    actual = image.size
                records.append({
                    "screen": screen.slug,
                    "number": screen.number,
                    "context": screen.context,
                    "app": screen.app,
                    "theme": theme,
                    "viewport": {"width": width, "height": height},
                    "actual_dimensions": {"width": actual[0], "height": actual[1]},
                    "path": out.relative_to(ROOT).as_posix(),
                    "sha256": sha256(out),
                    "bytes": out.stat().st_size,
                })
        browser.close()
    return records


def write_manifests(records: list[dict[str, Any]]) -> None:
    BASELINES.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "baseline_kind": "initial-local-baseline",
        "screens": len(SCREENS),
        "screenshots": len(records),
        "records": records,
    }
    (BASELINES / "visual-baseline-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (DOCS / "visual-regression-report.json").write_text(json.dumps({
        "status": "baseline_established",
        "comparison": "Nenhum baseline anterior foi fornecido; esta revisão estabelece a baseline inicial local.",
        "expected_screens": 40,
        "generated_screens": len({r['screen'] for r in records}),
        "generated_screenshots": len(records),
        "pixel_differences": None,
        "tenant_brand_leakage": "validated_by_scripts/visual/validate_visual_contract.py",
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    parser.add_argument("--skip-render", action="store_true")
    args = parser.parse_args()
    generate_sources()
    generate_reference_assets()
    records = [] if args.skip_render else render_previews(args.chromium)
    if records:
        write_manifests(records)
    print(json.dumps({"screens": len(SCREENS), "screenshots": len(records), "catalog": str(CATALOG / 'index.html')}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
