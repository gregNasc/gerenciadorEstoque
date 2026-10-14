# R2.F — Exclusividade de Custódia

## Estado

Subetapa implementada localmente em 08/10/2026.

## Escopo entregue

- Equipamento não pode participar de duas Custódias vigentes;
- Linha Móvel não pode participar de duas Custódias vigentes;
- os estados `ATIVA` e `EM_DEVOLUCAO` mantêm a reserva do ativo;
- Rascunho não reserva ativos;
- Finalização ou cancelamento libera o ativo sem apagar o item histórico;
- ativação de Rascunho conflitante é rejeitada sem alterar seu estado;
- constraints condicionais no banco protegem contra concorrência;
- mudança de estado sincroniza os itens dentro de transação atômica.

## Estratégia técnica

`ItemCustodia.vigente` materializa a vigência do estado da Custódia. Essa
materialização permite índices únicos condicionais para Equipamento e Linha
Móvel, algo que não pode ser expresso por constraint atravessando a chave
estrangeira até `Custodia.status`.

## Migration

`estoque.0067_itemcustodia_vigente_and_more` é aditiva: inclui `vigente`,
preenche itens existentes conforme o estado da Custódia e cria as constraints
de exclusividade. Se houver conflito legado, a migration interrompe com uma
mensagem explícita em vez de escolher silenciosamente qual vínculo preservar.

## Limite desta subetapa

Ainda não foram implementados:

- telas, formulários ou endpoints;
- devolução por item;
- Termos de Entrega/Devolução;
- DocuSign e notificações;
- compatibilidade com o campo legado `responsavel`.

## Validação

- testes acumulados R2.E/R2.F: 17/17;
- R2.A–R2.F + catálogo fail-closed + linhas móveis: 66/66;
- `python manage.py check`: aprovado durante os testes.

## STOP

Não houve commit, push, migration aplicada no banco local/produção ou deploy.
Não iniciar R2.G sem autorização.
