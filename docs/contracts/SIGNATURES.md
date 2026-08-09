# Contratos e assinaturas

Contrato gerado congela snapshot e PDF, calcula SHA-256 e cria envelope. O ciclo de vida do contrato é independente do ciclo de cada signatário.

A assinatura eletrônica interna registra consentimento, ator, data UTC, documento/hash, IP/user-agent quando autorizado e pacote de evidências. ICP-Brasil e GOV.BR são providers condicionais; ausência de credencial não bloqueia o restante.

O teste local gera PDF, assina envelope e valida por código público sem expor conteúdo sensível.
