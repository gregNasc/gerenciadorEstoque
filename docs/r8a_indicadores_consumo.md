# R8.A — Indicadores de consumo e planejamento

## Objetivo

Transformar o antigo painel resumido de Planejamento em uma leitura operacional
útil, sem custos e sem decisões automáticas de compra.

## Fontes oficiais

- **Solicitado:** `ItemSolicitacaoInsumo.quantidade`;
- **Atendido:** `ItemSolicitacaoInsumo.quantidade_atendida`;
- **Consumido:** `ConsumoInsumo.quantidade`, gerado pelos checklists;
- **Estoque atual:** `SaldoInsumoBase`;
- **Solicitações abertas:** estados acionáveis do fluxo R6.

Essas grandezas não são misturadas. O painel também não soma unidades de
medida diferentes em um total sem significado.

## Indicadores por item

- última solicitação;
- quantidade usual, calculada pela mediana;
- intervalo típico entre datas de solicitação, calculado pela mediana;
- quantidade solicitada, atendida e consumida no período;
- estoque atual, reservado e disponível;
- demanda anual estimada;
- tendência recente;
- cobertura aproximada em dias;
- referência de reposição para 30 dias.

Quando existe consumo, ele é a fonte preferencial da demanda. Sem consumo, o
atendimento é usado como aproximação e isso fica indicado na interface.

## Sugestões

As sugestões são exclusivamente informativas. Nenhum pedido, solicitação ou
quantidade de compra é preenchido automaticamente.

Prioridades:

1. sem estoque e com solicitação aberta;
2. cobertura estimada inferior a 30 dias;
3. estoque compatível com o histórico;
4. histórico insuficiente.

## Interface e exportação

- acesso pelo menu **Insumos → Planejamento de consumo**;
- filtros por empresa, Base, período, categoria e busca textual;
- empresa principal selecionada na primeira carga;
- tabela explicativa sem dependências JavaScript externas;
- exportação `.xlsx` com os mesmos filtros e sem qualquer coluna financeira.

## Permissões e isolamento

Podem acessar:

- Superuser;
- Admin;
- Compras;
- Planejamento;
- Executivo.

Gestor ou Operador sem perfil funcional não acessa o painel. Empresas e Bases
são derivadas da política de acesso e filtros fora do escopo retornam 403.
Nenhum preço, custo, valor unitário ou total financeiro faz parte do serviço.

## Desempenho

- consultas agregadas independentes evitam multiplicação de linhas entre
  solicitações, consumos e saldos;
- limites de data usam intervalos de `datetime`, preservando o uso de índices;
- a lista segura de Bases é calculada uma vez e reutilizada;
- catálogo é carregado em lote;
- teste impede crescimento de consultas por item (N+1);
- a página não depende de Chart.js ou outra biblioteca externa.

## Migrations

Nenhuma.
