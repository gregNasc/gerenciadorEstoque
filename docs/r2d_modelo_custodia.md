# R2.D — Modelo histórico de Custódia

## Estado

Subetapa implementada localmente em 08/10/2026.

## Escopo entregue

- entidade histórica `Custodia` vinculada explicitamente à empresa;
- vínculo obrigatório com Colaborador e Base;
- Local Físico opcional, mas obrigatoriamente relacionado à Base quando usado;
- data de entrega, estado, condição geral, observação e responsável pelo registro;
- estados Rascunho, Ativa, Em devolução, Finalizada e Cancelada;
- proteção contra exclusão dos relacionamentos históricos;
- validação tenant-aware de Colaborador e Base;
- policy de consulta e gestão baseada no `TenantScope` atual;
- ações desconhecidas falham fechadas.

## Migration

`estoque.0065_custodia` é aditiva e cria somente a tabela, constraints e
índices de `Custodia`. Nenhuma tabela ou coluna legada é removida ou alterada.

## Limite desta subetapa

Ainda não foram criados:

- itens de Custódia ou exclusividade de ativos;
- telas, formulários ou endpoints;
- fluxo de devolução;
- Termos de Entrega ou Devolução;
- integração DocuSign;
- notificações;
- alteração do campo legado `responsavel`.

## Segurança e compatibilidade

Custódias nunca são compartilhadas implicitamente entre empresas. A policy
respeita apenas empresas visíveis/gerenciáveis pelo escopo central e o modelo
valida que Colaborador e Base pertencem à empresa registrada.

## Validação

- testes direcionados R2.D: 8/8;
- R2.A–R2.D + catálogo fail-closed + linhas móveis: 49/49;
- `python manage.py check`: aprovado durante os testes.

## STOP

Não houve commit, push, migration aplicada no banco local/produção ou deploy.
Não iniciar R2.E sem autorização.
