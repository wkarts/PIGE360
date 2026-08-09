# Status das integrações

| Integração | Estado desta entrega | Execução real |
|---|---|---|
| PostgreSQL assíncrono | adapter e migrations preparados | não, servidor ausente |
| Redis/RabbitMQ/MinIO | contratos e Compose | não, runtime de containers ausente |
| Cloudflare/Tunnel/SaaS | providers/configuração desabilitados | não, sem rede/credenciais |
| Mailcow IMAP/SMTP/API | contrato desabilitado | não |
| Evolution API | adapter/configuração desabilitados | não |
| Bancos/PIX/CNAB | recursos, idempotência e contrato | não homologado |
| NF-e/NFC-e/NFS-e | domínio genérico, providers e storage contratados | não homologado com SEFAZ/município |
| IBPT | configuração e adapter previstos | nenhuma consulta realizada |
| GOV.BR | provider condicional e status `not_configured` | não homologado |
| ICP-Brasil | contrato/fixture e política | sem certificado real |
| Google Play/App Store | workflows condicionais | sem upload |

Mocks permanecem restritos a teste/homologação e não são apresentados como provider real.
