# Artefatos fiscais locais

O PIGE360 gera artefatos auxiliares locais para documentos fiscais sem confundir a geração do PDF com autorização fiscal. A autorização, consulta, cancelamento e eventos continuam dependendo do provider configurado e de homologação/produção reais.

## Tipos suportados

| Documento | Artefato | Content-Type |
|---|---|---|
| NF-e | `danfe_local` | `application/pdf` |
| NFC-e | `danfce_local` | `application/pdf` |
| NFS-e | `danfse_local` | `application/pdf` |

## Endpoints

Todos os endpoints exigem sessão autenticada, permissão fiscal/financeira e resolução do tenant pelo contexto da requisição.

```text
POST /api/v1/fiscal/documents/{document_id}/render
GET  /api/v1/fiscal/documents/{document_id}/artifacts
GET  /api/v1/fiscal/documents/{document_id}/artifacts/{artifact_id}/download
```

O endpoint de listagem informa o tipo, SHA-256, tamanho, data e disponibilidade do objeto. O download nunca aceita uma chave de storage fornecida pelo cliente; a aplicação resolve o artefato por `tenant_id`, `document_id` e `artifact_id`.

## Integridade

Antes de responder o download, o backend:

1. verifica o documento e o artefato no tenant autenticado;
2. lê o objeto privado do storage;
3. recalcula o SHA-256 do conteúdo recebido;
4. compara o digest com o valor persistido;
5. registra auditoria da leitura ou da divergência;
6. bloqueia a resposta com `FISCAL_ARTIFACT_INTEGRITY_FAILED` quando houver divergência.

A resposta válida inclui `X-Artifact-SHA256`, `X-Artifact-Bytes` e `Content-Disposition` com nome seguro derivado do tipo do artefato e do identificador do documento.

## Isolamento e operação

- Os objetos são gravados em `fiscal/{document_id}/rendered/...` dentro do storage do tenant.
- O artefato é derivado do snapshot persistido do documento e não substitui XML autorizado.
- O modo de contingência exibido no PDF é informativo e não constitui autorização SVC/EPEC.
- A interface administrativa permite listar e baixar os PDFs após a validação do hash pelo servidor.
