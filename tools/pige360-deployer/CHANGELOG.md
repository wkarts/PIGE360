# Changelog

## 1.1.2 - 2026-09-05

- Integra o PIGE360 Deployer ao monorepo principal da plataforma.
- Limita o agente remoto a Linux AMD64/x86_64.
- Coordena os instaladores desktop x64 com prereleases de `develop` e releases SemVer do PIGE360.

## 1.0.0 - 2026-09-05

- Cria a identidade independente PIGE360 Deployer.
- Porta a arquitetura desktop Tauri + agente Rust temporário do implantador de referência.
- Adiciona canais `develop`, `prerelease` e `stable` com política fail-closed para produção.
- Instala Compose, Dockge, CloudPanel e Portainer a partir dos deployments versionados do PIGE360.
- Verifica commit, SHA-1 dos blobs Git e SHA-256 do manifesto da distribuição.
- Implementa `plan`, `prepare`, instalação, update, readiness, recibo e rollback imutável.
- Preserva `.env`, secrets, volumes e estado; adiciona backup e restauração transacional.
- Adiciona SSH por chave/agent, validação de `known_hosts` e preflight de servidor.
- Adiciona credenciais opcionais GHCR, Cloudflare, túneis e Connect API sem persistência em recibos.
- Adiciona build do agente Linux AMD64 embutido nos instaladores desktop.
- Adiciona prerelease automática para cada push em `develop` e release SemVer coordenada.
- Mantém licenciamento desativado e serviços genéricos da base fora da operação.
