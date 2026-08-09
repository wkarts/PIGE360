# Mailcow no PIGE360

Modos suportados: `disabled`, `mailcow_managed`, `generic_imap_smtp` e `dedicated_mailcow`.

A API REST do Mailcow administra domínio, mailbox, aliases, quota e suspensão. IMAPS/SMTP tratam o conteúdo e o Mailcow permanece a fonte oficial das caixas. Metadados locais e funcionamento do cliente interno estão descritos em [INTERNAL_MAIL_CLIENT.md](./INTERNAL_MAIL_CLIENT.md).

O provisionamento automático é disparado somente por vínculo de trabalho ativo (`EmployeeEmploymentActivated`) e política habilitada do tenant. Senhas nunca chegam ao frontend e referências de segredo são resolvidas pelo backend.

DNS de e-mail deve permanecer **DNS only** na Cloudflare e incluir, conforme a implantação: MX, PTR, SPF, DKIM, DMARC, MTA-STS/TLS-RPT, autodiscover e autoconfig. A aplicação escolar e o servidor de e-mail não compartilham a mesma fronteira de exposição.

Nesta construção local nenhum Mailcow externo foi acessado. Providers e testes usam contratos/fakes locais; operação remota depende de `INTEGRATION_REMOTE_ENABLED=true` e configuração/segredos válidos no ambiente de destino.
