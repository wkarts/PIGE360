# Multi-tenancy

## Resolução obrigatória

O tenant é resolvido pelo hostname antes da autenticação. `X-Tenant-ID`, `tenant_id` em query string e seleção pública pelo frontend são rejeitados. Domínio desconhecido retorna 404.

## Separação física e lógica

- banco de controle separado;
- banco e usuário previstos por tenant em PostgreSQL;
- adapter local cria arquivo SQLite separado por tenant para comprovação sem infraestrutura externa;
- storage em `/var/lib/pige360/tenants/<uuid>`;
- buckets e chaves são derivados do UUID, nunca do nome comercial;
- RLS interno limita instituição, unidade, campus e departamento.

## Suporte global

O contrato exige sessão temporária com motivo, step-up, ator real e banner permanente. A rota genérica de dados nunca aceita token da plataforma dentro de um hostname tenant.

## Testes

A suíte prova que registros, tokens, arquivos, hostnames e backups não cruzam entre dois tenants locais. O relatório de backup/restore restaura somente Alpha e verifica ausência de Beta.
