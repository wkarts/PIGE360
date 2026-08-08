# ADR-002 — Tenant somente por hostname

**Status:** aceito.

O hostname é validado antes da autenticação e abertura de recursos. Cabeçalhos públicos ou parâmetros de tenant são proibidos para evitar confused-deputy e troca de contexto induzida pelo cliente. Domínios personalizados mapeiam para um único UUID imutável.
