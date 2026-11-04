# R7.E.1 — Conciliação da NF-e com o catálogo

## Objetivo

Localizar itens já conhecidos da empresa a partir do XML da NF-e, sem criar ou alterar cadastros sem confirmação humana.

## Entregas

- análise automática após a leitura ou releitura do XML;
- busca exata por EAN/GTIN, código do fornecedor e SKU legado;
- busca secundária por descrição exata no catálogo de equipamentos e nos insumos efetivamente usados pela empresa;
- isolamento integral por empresa durante a busca;
- estados visíveis: correspondência sugerida, confirmada ou não encontrada;
- confirmação explícita por Compras/Admin autorizado;
- registro de EAN/GTIN e código do fornecedor somente após a confirmação;
- proteção contra reassociar um código que já identifica outro item;
- confirmação idempotente e evento auditável sem valores financeiros;
- preservação das confirmações ao reler o mesmo XML;
- bloqueio para Gestor, usuário restrito e usuário de outra empresa;
- nenhum produto, equipamento ou insumo criado automaticamente.

## Banco de dados

A migração `compras.0010_itemnotafiscalaquisicao_codigo_catalogo_and_more` adiciona o estado de conciliação e as referências confirmadas aos itens da NF-e, além do tipo de código "Código do fornecedor".

## Validação executada

- 12 testes dirigidos de documentos, leitura e conciliação da NF-e;
- 72 testes do módulo Compras;
- 9 testes integrados de isolamento e terminologia;
- `manage.py check` sem erros;
- `makemigrations --check --dry-run` sem alterações pendentes.

## Próxima subetapa

R7.E.2 deve oferecer um fluxo assistido para itens não encontrados: escolher se o item é equipamento ou insumo, revisar os dados sugeridos e abrir o cadastro correspondente. A criação continuará dependendo de uma confirmação explícita.
