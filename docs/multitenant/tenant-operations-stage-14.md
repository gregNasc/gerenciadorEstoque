# Etapa 14 — SICK, transferências e empréstimos

## Resultado

A autorização de operações foi centralizada em
`TenantOperationPolicy`. Permissão funcional de tela e escopo de dados são
validados separadamente: possuir o papel funcional não concede acesso a outro
tenant.

| Fluxo | Origem e destino | Equipamento e histórico | Ações protegidas |
|---|---|---|---|
| SICK | Base do equipamento e Base de origem | SICK e histórico limitados ao equipamento visível | abertura, envio, manutenção e retorno |
| Transferência | ambas as Bases devem estar no escopo | itens somente da origem; histórico acompanha o equipamento | criação, aprovação, separação, recebimento e cancelamento |
| Empréstimo | ambas as Bases devem estar no escopo e no grupo regional | itens somente da origem; histórico acompanha o equipamento | criação, recebimento, devolução e confirmação |

## Operação entre empresas

Uma movimentação entre empresas distintas exige relacionamento direcional ativo
e capability exata `TRANSFERENCIAS:MOVIMENTAR` ou
`EMPRESTIMOS:MOVIMENTAR`. Uma operação dentro da mesma empresa não exige
relacionamento.

Para Admin, uma Base de empresa relacionada só entra no escopo se a empresa foi
selecionada no perfil e a capability da ação existe. Gestores e Operadores
continuam limitados às Bases explicitamente vinculadas. Apenas o Superuser da
plataforma possui escopo global explícito.

O relacionamento operacional não concede administração cross-tenant. Da mesma
forma, o grupo funcional de manutenção SICK não cria escopo global: seus membros
continuam sujeitos ao tenant e às Bases do perfil. SICK terceirizado permanece
restrito à Base de origem.

## Proteções de entrada

- IDs de operação são resolvidos em querysets já filtrados por tenant;
- IDs de Bases de origem/destino são validados antes da mutação;
- equipamentos forjados ou pertencentes a outra origem são recusados;
- recebimento, devolução e cancelamento validam novamente a Base responsável no
  serviço transacional;
- solicitações e aprovações de transferência usam apenas Bases autorizadas.

## Testes

`estoque/test_tenant_operations.py` cobre relacionamento direcional,
capability exata, Admin multiempresa, vínculo de Gestor/Operador, grupo de
manutenção SICK e IDs externos forjados.
