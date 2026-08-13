# Base do workspace local

Esta árvore foi reconstruída a partir do checkpoint canônico `r000031`, cuja integridade do pacote foi conferida por SHA-256 antes da extração.

## Inventário preservado

- 13 aplicações: administração, portais, família, professor, aluno, cantina, PDV, quiosque, ponto, desktop, console e estúdio de branding;
- 53 módulos backend de domínio;
- 15 workflows de CI/CD mantidos como arquivos locais;
- contratos, migrations, telas, integrações locais e documentação existentes preservados.

## Evoluções incorporadas

- artefatos fiscais locais para NF-e, NFC-e e NFS-e, com download autenticado, isolamento por tenant, SHA-256, auditoria e testes de integridade;
- correções de TypeScript sem desabilitar o modo estrito e sem incorporar arquivos compilados;
- workflows de frequência e segurança corrigidos, com lockfile raiz para instalação determinística;
- assinatura Android e iOS opcional, com preservação do artefato original quando faltar configuração ou a assinatura falhar;
- chamada digital de frequência com rascunho, versionamento, idempotência, envio auditado e fechamento controlado da sessão.
- rastreabilidade operacional de NFS-e para serviços: o evento fiscal por item agora referencia a montagem e o documento fiscal gerados, refletindo também o retorno do provider no pedido de serviço.
- recibos de pagamento de serviços: emissão automática para pagamentos e PIX conciliados, PDF privado com SHA-256, isolamento por tenant, auditoria, outbox, consulta, download e anulação que preserva o histórico financeiro.

## Limites da árvore local

Não há publicação, deploy, registro remoto ou execução de imagens OCI neste workspace. O validador registra a ausência do manifesto OCI como item não executado, sem mascarar a condição como artefato produzido.
