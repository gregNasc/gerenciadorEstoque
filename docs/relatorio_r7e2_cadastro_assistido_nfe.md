# R7.E.2 — Cadastro assistido a partir da NF-e

## Objetivo

Permitir que Compras trate itens fiscais não encontrados sem transformar automaticamente a NF-e em cadastro técnico.

## Entregas

- ações separadas para cadastrar equipamento ou insumo quando o item não for encontrado;
- formulário de equipamento preenchido com empresa, código, descrição, SKU e unidade sugeridos pelo XML;
- formulário de insumo preenchido com descrição, termo de pesquisa, unidade e Base sugerida;
- empresa fixada ao escopo da aquisição durante o cadastro de equipamento;
- Base obrigatória e limitada à empresa da aquisição durante o cadastro de insumo;
- aviso claro de que o cadastro só ocorre após salvar o formulário;
- retorno automático à aquisição após o cadastro confirmado;
- vínculo do novo cadastro ao item da NF-e e registro dos códigos fiscais;
- operação atômica: falha de escopo ou vínculo desfaz o novo cadastro;
- bloqueio para item já sugerido/confirmado, usuário restrito, Gestor e outra empresa;
- nenhum preço da NF-e é transferido automaticamente para o catálogo.

## Banco de dados

Esta subetapa reutiliza a estrutura criada pela migração `compras.0010`; não cria uma migration adicional.

## Validação executada

- 7 testes dirigidos da conciliação e do cadastro assistido;
- 75 testes do módulo Compras;
- 24 testes combinados de Insumos, EPI, permissões, isolamento e terminologia;
- `manage.py check` sem erros;
- `makemigrations --check --dry-run` sem alterações pendentes.

## Próxima etapa

Com a R7.E concluída, a sequência do plano passa para R7.F: recebimento inteligente, comparando aquisição, NF-e e conferência física, incluindo entregas parciais e divergências.
