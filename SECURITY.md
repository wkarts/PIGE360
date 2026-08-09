# Segurança

Reporte vulnerabilidades de forma privada ao responsável operacional definido na instalação. Não inclua segredos, dados reais de estudantes ou evidências contendo dados pessoais em chamados públicos.

Controles implementados incluem resolução do tenant por hostname, rejeição de seletores públicos de tenant, JWT com audiência, refresh rotativo, Argon2, RBAC, auditoria, idempotência, armazenamento segregado, validação de upload, proteção de caminhos e configuração remota desabilitada por padrão.

A ativação em produção exige secret manager, PostgreSQL, TLS, proxy confiável, WAF, varredura de containers, antivírus operacional, backups criptografados e testes de restauração no ambiente alvo.
