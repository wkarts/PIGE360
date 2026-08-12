# Estado inicial da execução

## Identificação

- Produto: **PIGE360 — Plataforma Integrada de Gestão Educacional**
- Pronúncia registrada: **píge três meia zero**
- Início da execução local: `2026-08-09T10:03:37.512469+00:00`
- Workspace: `/mnt/data/pige360`
- Contrato V8: `PROMPT_FINAL_COMPLETO_PIGE360_V8_LOCAL_SEM_REPOSITORIO(1).md`
- SHA-256 do contrato: `33d177211b3cfd4b80a19a61f351d5bd02950003bf2cda1d448a369e6686bc27`
- Acervo visual: `PIGE360_BRANDING_COMPLETO(1).zip`
- SHA-256 do acervo visual: `df59b518bad9f88b607e7ec5d3f429e3e6c09f6369f1ea5b6f7f74451b117a38`

## Estado encontrado

O workspace de implementação não existia. Em `/mnt/data` estavam disponíveis somente o contrato V8 e o arquivo ZIP do branding oficial. Não havia código-fonte, manifests, Dockerfiles, Compose, migrations, lockfiles, documentação operacional, builds ou artefatos de release preexistentes para preservar.

## Inventário dos anexos

- Contrato V8 em Markdown: UTF-8, 6.410 linhas, 139.684 bytes.
- Branding oficial: ZIP íntegro, 119 entradas, 24.889.926 bytes descompactados.
- Checksums internos do branding: todos aprovados.
- Ativos encontrados: logos PNG/SVG, ícones Android/iOS/Linux/macOS/Windows/PWA, favicons, splash screens, peças sociais, branding por aplicativo, papelaria, pranchas, referências visuais, design tokens e manifestos.

## Regra nominal mais recente

Somente a marca **PIGE360** e sua descrição oficial podem aparecer em código, documentação, interfaces, metadados, relatórios, instaladores e artefatos. Qualquer denominação nominal anterior está proibida e não será copiada para os artefatos operacionais.

## Toolchains locais

- Python 3.13.5: disponível.
- FastAPI, SQLAlchemy 2, Alembic, Pydantic, Uvicorn, Pytest, HTTPX, Argon2, Cryptography, OpenPyXL e ReportLab: disponíveis.
- Node.js 22.16.0, npm 10.9.2 e TypeScript global: disponíveis.
- Runtime Vue 3 local proveniente de pacote já instalado: disponível para build sem rede.
- Docker/Compose: indisponíveis no host atual.
- Rust/Cargo: indisponíveis no host atual.
- Toolchains Android/iOS/macOS/Windows: indisponíveis no host Linux atual.
- Acesso remoto: não utilizado.

## Riscos iniciais comprovados

1. O projeto precisa ser criado integralmente a partir do zero.
2. Builds OCI não podem ser executados sem Docker ou runtime compatível.
3. Builds Tauri/Rust e mobile nativos não podem ser executados sem toolchains correspondentes.
4. Dependências ausentes não podem ser obtidas por rede nesta execução; os caminhos locais devem usar somente o que já está instalado.
5. Parte das referências visuais é apenas material de auditoria e não será incorporada diretamente às interfaces, evitando qualquer resíduo nominal não autorizado.
