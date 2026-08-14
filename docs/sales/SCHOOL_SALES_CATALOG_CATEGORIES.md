# Categorias do catálogo comercial escolar

O catálogo de produtos do PIGE360 passou a registrar uma categoria escolar independente do tipo legado de produto. A categoria não altera preço, estoque, fiscal, baixa, devolução ou o fluxo de vendas já existente.

## Categorias suportadas

| Categoria | Uso comercial |
| --- | --- |
| `school_uniform` | Fardamento e uniformes |
| `textbook` | Livros |
| `handout` | Apostilas |
| `learning_module` | Módulos didáticos |
| `educational_material` | Materiais escolares |
| `school_kit` | Kits escolares |
| `event_ticket` | Ingressos |
| `event` | Produtos vinculados a eventos |
| `general` | Produtos diversos |

## Compatibilidade

Produtos legados mantêm `product_type`. Quando uma categoria não é enviada no cadastro, a API converte `uniform`, `book`, `material` e `kit` para as categorias escolares equivalentes; os demais usam `general`.

O filtro opcional `school_catalog_category` em `GET /api/v1/products` retorna somente produtos do tenant autenticado. A categoria é persistida junto ao produto e toda venda continua usando o mesmo produto, estoque, caixa, auditoria, outbox e fluxo fiscal já existentes.

## Migração

A migration tenant `0044_school_sales_catalog_categories` adiciona a coluna com valor padrão compatível, classifica produtos legados conhecidos e cria índice por tenant, categoria e estado. O downgrade remove somente o índice, preservando a classificação comercial gravada.
