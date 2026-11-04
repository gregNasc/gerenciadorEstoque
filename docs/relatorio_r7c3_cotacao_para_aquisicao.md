# Relatório R7.C.3 — Conversão controlada de cotação em aquisição

## Objetivo

Conectar a proposta escolhida ao domínio de Aquisições sem criar compras
automaticamente e sem perder a rastreabilidade da Solicitação R6.

## Fluxo implementado

```text
Cotação decidida
    ↓
Solicitação aprovada
    ↓
Confirmação humana para gerar aquisição
    ↓
Aquisição em rascunho
    ↓
Revisão e aprovação da aquisição
    ↓
Solicitação passa para Pedido realizado
```

A decisão da cotação, isoladamente, não cria uma aquisição. A geração exige uma
ação explícita, uma caixa de confirmação e uma solicitação previamente aprovada.

## Rastreabilidade preservada

- Empresa e Base de destino da solicitação.
- Processo de cotação e proposta escolhida.
- Fornecedor homologado.
- Itens cotados e referências do catálogo.
- Quantidade e valor unitário por item.
- Frete, impostos e desconto no nível correto da proposta.
- Número do pedido de compra, centro de custo e observação, quando informados.
- Usuário e evento de criação da aquisição.

## Regras de integridade

- Uma cotação gera no máximo uma aquisição.
- Um item cotado gera no máximo um item de aquisição.
- Reenvio ou duplo clique retorna a aquisição existente, sem duplicar dados.
- A proposta precisa ser a escolhida no processo.
- O fornecedor precisa continuar ativo e homologado.
- A Base precisa pertencer à empresa da aquisição.
- Novos itens precisam estar vinculados ao catálogo antes da conversão.
- Gestor, Operador comum, outro grupo empresarial e `jose.barboza` não podem
  acessar valores nem gerar a aquisição.

## Interface

- A tela de cotação explica que a decisão é humana.
- Depois da decisão e aprovação da solicitação, apresenta a confirmação para
  gerar o rascunho.
- Quando a aquisição já existe, mostra apenas o acesso à aquisição vinculada.
- A tela de aquisição mostra origem, Base, itens e composição legível do total.
- Solicitações com cotação não usam o atalho legado “Encaminhar para compra”; o
  usuário retorna ao fluxo rastreável da cotação.

## Terminologia para usuários

O termo técnico `tenant` foi removido das telas comuns. Um teste de regressão
agora impede seu uso em templates acessíveis a usuários que não sejam
Superadmin. O termo permanece permitido apenas no painel e onboarding exclusivos
do Superadmin.

## Banco de dados

Migration aditiva:

- `compras.0007_aquisicao_base_destino_aquisicao_desconto_cotacao_and_more`

A migration adiciona referências opcionais e valores com padrão zero. Não
remove tabelas, colunas ou registros existentes.

## Validação executada

- Testes específicos de cotações e conversão: 12/12 aprovados.
- Suíte completa de Compras: 60/60 aprovados.
- Testes integrados R6/K.1/K.2/R7.C.1: 33/33 aprovados.
- Regra de terminologia dos templates: 1/1 aprovada.
- `manage.py check`: sem problemas.
- `makemigrations --check --dry-run`: nenhuma alteração pendente.
- `git diff --check`: sem erros.

Total consolidado: **94 testes distintos aprovados**.

## Estado

R7.C.3 concluída localmente. Nenhum commit, push ou deploy foi realizado. A nova
migration `0007` ainda precisa ser aplicada nos ambientes que receberem esta
subetapa.
