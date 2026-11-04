# R7.D.2 — Leitura estruturada da NF-e

## Objetivo

Ler o XML oficial da NF-e como fonte estruturada, apresentar seus dados para conferência e preservar o catálogo contra cadastros automáticos ou duplicados.

## Entregas

- processamento automático do XML válido ao cadastrar a aquisição;
- ação manual para processar ou conferir novamente documentos já existentes;
- snapshot auditável do cabeçalho e dos itens da NF-e;
- extração de emitente, CNPJ, número, série, chave, data, produtos, código do fornecedor, EAN/GTIN, NCM, CFOP, unidade, quantidade e valores;
- totalização de produtos, frete, desconto, tributos destacados e total da nota;
- detecção de divergência de chave, número do documento e CNPJ do fornecedor;
- preenchimento apenas dos campos vazios de chave e número da aquisição;
- preservação de dados manuais divergentes para conferência humana;
- reprocessamento idempotente pelo hash SHA-256 do XML;
- evento auditável `NFE_PROCESSADA` somente quando o conteúdo muda;
- nenhuma criação automática de produto, insumo ou código de catálogo;
- bloqueio de leitura e processamento para Gestor, usuário restrito e usuário de outra empresa.

## Interface

A tela de aquisição mostra os dados extraídos, divergências e itens fiscais somente a usuários autorizados a acessar documentos financeiros. O texto informa expressamente que a leitura não cadastra produtos automaticamente.

## Banco de dados

A migração `compras.0009_notafiscalaquisicao_itemnotafiscalaquisicao_and_more` cria os snapshots da nota e de seus itens. Ela não altera aquisições ou documentos existentes; XMLs antigos podem ser processados pela ação de conferência após a migração.

## Validação executada

- 8 testes dirigidos de upload privado e leitura estruturada;
- 68 testes do módulo Compras;
- 9 testes integrados de isolamento e terminologia;
- `manage.py check` sem erros;
- `makemigrations --check --dry-run` sem alterações pendentes.

## Próxima etapa

R7.E deve resolver os itens lidos contra EAN/GTIN, código do fornecedor e catálogo existente. Itens não encontrados devem ser apenas sugeridos e continuar dependendo de confirmação humana.
