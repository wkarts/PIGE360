# Offline e sincronização

Cada usuário/tenant possui banco local e chave no secure storage. A transação local grava alteração e outbox. O servidor recebe idempotency key, valida revisão e responde com checkpoint. Conflitos não são sobrescritos silenciosamente.

Planejamento e chamada armazenam somente turmas/períodos autorizados. Período fechado rejeita atualização. Logout revoga token e limpa dados conforme política. Anexos temporários permanecem criptografados.
