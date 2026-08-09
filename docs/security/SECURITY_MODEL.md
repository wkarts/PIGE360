# Segurança e LGPD

## Controles implementados

- Argon2id para senha e JWT curto com refresh rotativo;
- hostname confiável como fronteira do tenant;
- RBAC granular e pontos de ABAC contextual;
- correlation/request ID, auditoria antes/depois e motivo;
- idempotency key em mutações críticas;
- sanitização SVG e upload com hash;
- CSP no frontend servido por Nginx;
- containers não root, filesystem read-only e redes internas;
- secrets somente por arquivo/secret manager;
- logs sem payload sensível por padrão;
- backup isolado e verificação de hash;
- scanner local de padrões de segredo.

## Controles preparados

2FA/passkeys, HSM/KMS, antivírus ClamAV, certificate pinning, WAF, rate limit de borda, PAdES/ICP-Brasil e providers governamentais possuem contratos/configuração, mas exigem infraestrutura e homologação.

## Dados de menores

Acesso a saúde, localização, biometria, fotos e medicação deve depender de finalidade, base legal, consentimento quando aplicável, escopo de papel e auditoria de visualização. Nenhum desses providers fica habilitado por padrão.
