# Governança e importação versionada de catálogos fiscais

## Objetivo

Este incremento adiciona uma camada de governança para catálogos fiscais oficiais sem acoplar o domínio a uma URL, layout ou órgão específico. O mecanismo complementa os catálogos versionados existentes e mantém cada fonte, importação, snapshot, publicação, rollback e quarentena vinculados ao tenant.

## Catálogos suportados

- NCM;
- NBS;
- LC 116;
- CFOP;
- CEST;
- CST;
- CSOSN;
- CST IBS/CBS;
- cClassTrib;
- cBenef;
- crédito presumido;
- tabelas RTC.

As classificações continuam semanticamente separadas. O fato de dois catálogos possuírem códigos parecidos não cria equivalência automática entre eles.

## Perfis de origem

`fiscal_catalog_source_profiles` registra a origem de maneira versionada:

- `local_file`: importação explícita de arquivo local;
- `external_http`: contrato para fonte HTTP externa, mantido em `not_configured` até existir configuração válida;
- `manual_snapshot`: snapshot administrado localmente.

O perfil registra provider, versão do provider, formato, encoding, delimitador, referência, mapeamento de campos, schema de validação, política de idade máxima e histórico de saúde. Segredos não fazem parte do perfil; providers externos devem usar referência segura de configuração quando forem implementados/ativados.

## Importadores locais

### CSV

O parser usa encoding e delimitador do perfil. O mapeamento determina campos de código, descrição, parent e metadados adicionais.

### JSON

Aceita array de objetos ou um `root_path` configurado no mapping. Os objetos são normalizados pelo mesmo pipeline dos demais formatos.

### XSD

O parser usa `xml.etree.ElementTree` e extrai valores de `xs:enumeration`, incluindo documentação quando disponível. Arquivos contendo DTD/ENTITY são rejeitados antes do parse para evitar expansão de entidades.

## Pipeline

```text
arquivo local
→ validação de tamanho/nome/formato
→ SHA-256 do payload bruto
→ armazenamento do snapshot no storage exclusivo do tenant
→ parser do provider/formato
→ normalização
→ validação pelo schema do perfil + regex/normalizador do catálogo
→ diff contra a versão ativa
→ versão fiscal draft
→ entradas imutáveis
→ publicação explícita ou agendada
→ auditoria + outbox
```

O arquivo original é preservado em:

```text
fiscal/catalogs/<catalog_id>/imports/<run_id>/<filename>
```

A aplicação nunca depende de consultar a fonte remota durante uma venda.

## Snapshot e diff

Cada importação persiste:

- SHA-256 do payload original;
- tamanho e nome;
- versão do parser/provider;
- quantidade de linhas lidas/aceitas/rejeitadas;
- snapshot da configuração usada;
- diff contra a versão ativa (`added`, `removed`, `changed`);
- referência da versão de catálogo gerada.

O diff é informativo e auditável; a publicação continua sendo uma transição explícita.

## Publicação e vigência

Uma versão importada pode permanecer `draft`, ser publicada imediatamente ou ficar `scheduled` quando sua vigência é futura. Ao publicar uma versão corrente, a versão ativa anterior é superseded e a referência ativa do catálogo é atualizada na mesma transação.

Importação nunca altera silenciosamente uma versão já publicada.

## Rollback

Rollback não reativa nem modifica retroativamente o registro histórico. O sistema clona a versão selecionada para uma **nova versão**, preserva a versão histórica original e publica/agendada a nova cópia. Isso mantém cadeia temporal e auditabilidade.

## Quarentena

Falhas de parse/validação preservam o payload bruto em:

```text
quarantine/fiscal-catalogs/<catalog_id>/<run_id>/<filename>
```

A quarentena registra SHA-256, motivo, estado e vínculo com a importação. Um arquivo inválido não altera `active_version_id` e não substitui a última versão válida.

Estados de resolução são auditáveis, incluindo descarte administrativo.

## Health e expiração

`GET /api/v1/fiscal/catalog-governance/health` consolida, por catálogo:

- existência e vigência da versão ativa;
- perfis de origem configurados;
- provider `not_configured`;
- idade da última sincronização/importação bem-sucedida;
- quarentenas abertas;
- tipos de catálogo ainda ausentes.

Não existe health fictício: um provider HTTP sem configuração aparece explicitamente como não configurado.

## APIs

```text
GET    /api/v1/fiscal/catalog-sources
POST   /api/v1/fiscal/catalogs/{catalog_id}/sources
GET    /api/v1/fiscal/catalog-imports
POST   /api/v1/fiscal/catalogs/{catalog_id}/imports
GET    /api/v1/fiscal/catalog-imports/{run_id}
POST   /api/v1/fiscal/catalog-imports/{run_id}/publish
POST   /api/v1/fiscal/catalogs/{catalog_id}/versions/{version_id}/rollback
GET    /api/v1/fiscal/catalog-governance/health
GET    /api/v1/fiscal/catalog-quarantine
POST   /api/v1/fiscal/catalog-quarantine/{quarantine_id}/resolve
```

## Multi-tenancy e segurança

As tabelas novas possuem `tenant_id`, RLS e `FORCE ROW LEVEL SECURITY` no PostgreSQL. Toda consulta da camada de aplicação exige o tenant resolvido pelo runtime. O storage é obtido pelo `DataRouter` do tenant, evitando path escolhido diretamente pelo cliente.

## Auditoria e outbox

Criação de fonte, importação, quarentena, publicação, rollback e resolução administrativa registram eventos/auditoria na mesma unidade transacional correspondente ao estado relacional. Operações reutilizáveis possuem chave de idempotência.

## Limites e status externo

Este incremento comprova o **mecanismo local versionado de importação/governança**. Ele não declara que NCM, NBS, RTC ou qualquer outra tabela foi sincronizada/homologada junto a uma fonte oficial externa nesta execução. Providers HTTP permanecem `not_configured` enquanto endpoints/credenciais/contratos reais não estiverem configurados e validados.
