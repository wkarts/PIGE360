# Evidência — entrega de artefatos fiscais

Data: `2026-08-12`

## Implementado

- Renderização local determinística para `NF-e/DANFE`, `NFC-e/DANFC-e` e `NFS-e/DANFSe`.
- Listagem autenticada e limitada ao tenant do documento.
- Download autenticado com nome de arquivo, tipo MIME, tamanho e SHA-256 persistido.
- Rejeição do download quando o objeto armazenado diverge do SHA-256 registrado.
- Auditoria e outbox para renderização, download e falha de integridade.
- Interface Tenant Admin com consulta de artefatos e download do PDF.
- Contratos OpenAPI JSON/YAML e métodos do SDK atualizados para as duas rotas novas.

## Validações executadas

- `python -m compileall -q backend/app backend/tests scripts/execution scripts/frontend scripts/api` — aprovado.
- `python -m py_compile ...document_delivery_service.py ...router.py ...test_fiscal_delivery_resilience_rendering.py` — aprovado.
- `python -m json.tool docs/api/openapi.json` — aprovado.
- `python -m json.tool packages/api-sdk/src/generated/operations.json` — aprovado.
- PyYAML carregou `docs/api/openapi.yaml` sem erro.
- Busca literal no workspace por nomes e vestígios operacionais removidos — nenhum resultado.

## Limitações do ambiente

- A suíte direcionada não foi executada porque `pytest` não está instalado no runtime disponível.
- O validador Vue alcançou a etapa de verificação TypeScript, mas `tsc` não está instalado.
- A exportação automática do OpenAPI não foi executada porque FastAPI não está instalado.

As limitações acima estão registradas como pendência de execução, não como aprovação fictícia.
