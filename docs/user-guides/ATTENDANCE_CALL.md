# Chamada digital

A administração do tenant possui um fluxo completo para registrar a frequência de uma sessão de aula.

## Fluxo operacional

1. Abra **Frequência** e agende uma sessão com turma, componente, política e professor atribuído.
2. Na área **Chamada digital**, selecione a sessão.
3. Preencha a situação de cada aluno. O estado inicial é `Pendente` para impedir o envio acidental de uma chamada incompleta.
4. Use **Marcar todos presentes** quando essa for a regra da aula e ajuste as exceções individualmente.
5. Use **Salvar rascunho** para persistir a chamada com idempotência, versão e trilha de auditoria.
6. Quando não houver alunos pendentes, use **Enviar chamada**. A sessão passa a aceitar o fechamento.
7. Feche a sessão somente depois do envio. A coordenação pode reabrir uma sessão fechada para uma correção auditada.

## Segurança e consistência

- A API valida o tenant, a turma, a matrícula ativa e a atribuição docente.
- O salvamento usa `Idempotency-Key`.
- Cada chamada e cada registro preservam versões e eventos de auditoria.
- A chamada enviada não é sobrescrita silenciosamente; correções seguem o endpoint e a permissão correspondente.
