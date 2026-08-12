# Ciclo de vida de documentos fiscais e providers condicionais

## Objetivo

O incremento 0038 amplia o domínio fiscal existente sem simular autorização oficial. A emissão real continua condicionada a um provider configurado e ao transporte externo habilitado no runtime apropriado.

## Providers

Contratos suportados:

- `SefazNfeProvider` — NF-e;
- `SefazNfceProvider` — NFC-e;
- `NationalNfseProvider` — NFS-e padrão nacional;
- `MunicipalNfseProvider` — NFS-e municipal;
- `ThirdPartyFiscalProvider` — gateway fiscal explicitamente configurado.

Os adapters utilizam o contrato `FiscalApiProvider` e agora suportam `issue_document`, `query_document`, `cancel_document`, `substitute_document`, `inutilize_numbers` e `register_event`.

A aplicação local não presume homologação. Quando I/O externo está desabilitado, o health retorna `configured_unchecked`; quando endpoint, segredo ou certificado obrigatório não estão disponíveis, o status permanece `not_configured` ou `expired_certificate`.

## Certificado A1

O banco guarda somente metadados e a referência lógica do segredo:

- titular;
- CPF/CNPJ;
- serial;
- emissor;
- validade;
- fingerprint SHA-256;
- `secret_ref`.

O PFX e senha não são aceitos pelas APIs de cadastro e não são enviados ao frontend. A resolução de segredo é restrita ao diretório seguro do runtime.

## Estados e operações

O documento conserva o snapshot fiscal e registra:

- solicitação;
- configuração/ausência do provider;
- tentativas por operação;
- autorização/rejeição;
- consulta;
- cancelamento;
- substituição;
- eventos;
- contingência declarada;
- artefatos XML/PDF e SHA-256.

A substituição cria um novo documento e mantém os vínculos `replacement_of_document_id` / `substituted_by_document_id`; o documento original não é sobrescrito.

## Inutilização

A inutilização é um agregado próprio para NF-e/NFC-e, contendo ambiente, ano, série, intervalo, justificativa, provider, estado, protocolo, tentativas e auditoria. Sem provider configurado, o registro permanece `awaiting_provider_configuration` e nenhuma autorização é simulada.

## Persistência 0038

- `fiscal_certificate_metadata`;
- `fiscal_provider_configurations`;
- `fiscal_document_attempts`;
- `fiscal_document_artifacts`;
- `fiscal_inutilization_requests`;
- `fiscal_provider_event_requests`.

Todas as tabelas novas são tenant-scoped; a migration PostgreSQL habilita e força RLS e cria policy por `app.tenant_id`.

## Artefatos

Artefatos do provider são armazenados no object storage exclusivo do tenant. A tabela de artefatos registra tipo, MIME, key, tamanho e SHA-256. O payload persistido do provider remove XML/PDF inline e tokens/segredos não são gravados como evidência.

## Testes

Os testes usam transporte fixture exclusivamente local. Eles comprovam emissão, consulta, evento, substituição, inutilização, XML/PDF com hash, idempotência, isolamento cross-tenant, `not_configured` e migration/RLS. Esses testes não representam homologação SEFAZ, NFS-e nacional ou municipal.

## Limites externos

A autorização oficial requer, conforme provider, credenciais, certificado, endpoints/ambientes oficiais e conectividade habilitada. Na ausência desses requisitos o sistema continua construível/testável e mantém o provider desabilitado ou `not_configured`, em vez de usar mock de produção.
