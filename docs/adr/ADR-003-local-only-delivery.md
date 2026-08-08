# ADR-003 — Construção exclusivamente local

**Status:** aceito para esta revisão.

Nenhum repositório, registro, loja, provedor de deploy ou serviço externo foi acessado. Workflows são arquivos inertes. A ausência de toolchain nativa gera `skipped_not_configured`; não gera binário falso. A provenance registra essa restrição.
