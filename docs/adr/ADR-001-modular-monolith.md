# ADR-001 — Monólito modular

**Status:** aceito.

Foi escolhido um monólito modular porque os domínios educacionais compartilham transações e regras fortes. Processos de worker, scheduler, gateway e clientes são separados, mas não há fragmentação prematura em dezenas de serviços. Extração futura exige porta, evento e ownership claro, não repository genérico obrigatório.
