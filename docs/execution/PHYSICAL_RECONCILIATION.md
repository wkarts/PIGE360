# Reconciliação física do workspace

Gerada em `2026-08-12` após a inspeção do checkpoint integral `r000031` e a criação da cópia de trabalho local.

## Fonte utilizada

- Arquivo de origem: `PIGE360-workspace-checkpoint-1.0.0-r000031-20260811T121335Z(1).zip`.
- Prompt funcional: `PROMPT_FINAL_COMPLETO_PIGE360_V8_LOCAL_SEM_REPOSITORIO.md`.
- Revisões anteriores foram tratadas somente como histórico; nenhuma árvore anterior foi restaurada sobre o conteúdo mais novo.

## Limpeza aplicada

- Removida a pasta operacional de continuidade e seus checkpoints, estados, scripts, schedules e evidências.
- Removido o manifesto de empacotamento que inventariava essa pasta.
- Removidas evidências históricas cujo conteúdo dependia exclusivamente do mecanismo de continuidade.
- Atualizados os scripts de checkpoint/reconciliação para não dependerem de estado externo.
- Mantidas as evidências de aplicação: migrations, regressão, OpenAPI, branding, segurança e testes fiscais.

## Inventário físico importado

```text
versão declarada: 1.0.0
OpenAPI do checkpoint de origem: 557 paths / 687 operações / 375 schemas
backend: FastAPI + SQLAlchemy/SQLite de testes + PostgreSQL de produção
migrations do Tenant Plane: até 0041
aplicações PWA/Tauri: 13
regressão importada: 72 arquivos / 167 passed / 0 failed files
```

Os números acima são o último estado registrado no artefato de origem. Os resultados desta rodada serão registrados somente após execução real dos comandos no workspace limpo.

Após a implementação local de listagem e download de artefatos fiscais, o contrato versionado passou a registrar `559` paths, `689` operações e `375` schemas. A geração automática em runtime não foi executada porque FastAPI não está instalado neste ambiente; os arquivos JSON/YAML e o SDK foram atualizados de forma sincronizada e validados sintaticamente.

## Critérios de integridade

- nenhum segredo real ou certificado privado no pacote;
- nenhum caminho absoluto obrigatório para execução;
- isolamento de tenant mantido nas APIs de documentos e artefatos;
- artefatos fiscais armazenados por chave tenant-scoped e protegidos por SHA-256;
- providers oficiais permanecem condicionais e não são tratados como homologados sem configuração real.
