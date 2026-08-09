# OpenAPI e SDK TypeScript

`docs/api/openapi.json` e `.yaml` são exportados diretamente da aplicação. O SDK em `packages/api-sdk/src/generated` contém tipos e 324 métodos gerados. A validação impede `operationId` duplicado.

A autenticação envia Bearer token, mas o tenant continua sendo determinado pelo hostname da URL; o SDK não oferece parâmetro público de tenant.
