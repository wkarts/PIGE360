# Cliente de e-mail interno do PIGE360

## Fonte de verdade

O PIGE360 **não replica a caixa completa no PostgreSQL**. Em `mailcow_managed`, `dedicated_mailcow` ou `generic_imap_smtp`, o servidor IMAP continua sendo a fonte oficial do conteúdo. O banco do tenant mantém somente:

- vínculo da conta com o usuário/pessoa;
- pastas e cursor de sincronização por UID;
- cabeçalhos e metadados necessários à pesquisa/listagem;
- flags, tamanho, preview curta e SHA-256 técnico;
- drafts criados dentro do PIGE360;
- execuções de sincronização;
- delegações e auditoria.

O corpo integral e os bytes dos anexos são buscados do IMAP sob demanda. `mail_message_metadata` não possui colunas `body_text` ou `body_html`.

## Configuração

O tenant cadastra uma `integration_connection` com provider `generic_imap_smtp`, `mailcow` ou `MailcowProvider`. Exemplo de `config`:

```json
{
  "imap_host": "mail.escola.example",
  "imap_port": 993,
  "smtp_host": "mail.escola.example",
  "smtp_port": 587,
  "smtp_tls": "starttls",
  "timeout_seconds": 20,
  "allow_private_network": false
}
```

Em self-hosted de servidor único, `IMAP_HOST`, `IMAP_PORT`, `SMTP_HOST`, `SMTP_PORT` e `SMTP_TLS` de `.env` funcionam como defaults. Configuração específica do tenant tem precedência.

A senha da mailbox nunca é gravada no PostgreSQL nem enviada ao frontend. `mail_accounts.credential_secret_reference` aponta para um segredo com conteúdo JSON:

```json
{
  "username": "usuario@escola.example",
  "password": "senha-de-aplicativo"
}
```

Em produção, a referência é resolvida somente dentro de `/run/secrets`; path traversal é rejeitado.

## Segurança de rede

- TLS obrigatório para IMAP e SMTP (`IMAPS` / `STARTTLS` ou SMTPS).
- Hosts locais, privados, link-local e reservados são bloqueados por padrão para mitigar SSRF.
- Uma conexão interna de Mailcow somente pode usar rede privada se `allow_private_network=true` for configurado explicitamente naquela integração.
- Em `APP_ENV=testing`, transporte remoto permanece desabilitado e testes usam transporte fake local.
- Credenciais, corpo integral e tokens não entram nos logs estruturados.

## Operações implementadas

- health IMAP;
- descoberta de pastas;
- sincronização incremental por UID;
- listagem e pesquisa por pasta;
- leitura do corpo sob demanda;
- lido/não lido;
- mover entre pastas;
- mover para lixeira;
- download de anexos com SHA-256;
- envio SMTP idempotente;
- responder e responder a todos com `In-Reply-To`;
- encaminhar;
- drafts versionados;
- delegação read-only ou read/send, com vigência e revogação;
- auditoria e eventos de domínio.

## Endpoints principais

```text
GET    /api/v1/mail/me/status
POST   /api/v1/mail/me/health
POST   /api/v1/mail/me/sync
GET    /api/v1/mail/me/messages
GET    /api/v1/mail/me/messages/{id}
POST   /api/v1/mail/me/messages/{id}/seen
POST   /api/v1/mail/me/messages/{id}/move
POST   /api/v1/mail/me/messages/{id}/trash
POST   /api/v1/mail/me/messages/{id}/reply
POST   /api/v1/mail/me/messages/{id}/forward
GET    /api/v1/mail/me/messages/{id}/attachments/{index}
POST   /api/v1/mail/me/send
GET    /api/v1/mail/me/drafts
POST   /api/v1/mail/me/drafts
PATCH  /api/v1/mail/me/drafts/{id}
POST   /api/v1/mail/me/drafts/{id}/send
```

Administração de delegações e contas exige role administrativa/mail_admin. Acesso delegado é sempre limitado ao mesmo tenant.

## Mailcow

A API administrativa do Mailcow provisiona/suspende mailbox, aliases e quota. Ela **não** é usada para ler o conteúdo da caixa. Leitura continua em IMAPS e envio em SMTP Submission/SMTPS.
