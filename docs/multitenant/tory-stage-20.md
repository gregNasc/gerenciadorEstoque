# Etapa 20 — Tory e Tenant Scope

## Estado: concluída

A Tory recebe o `TenantScope` autorizado da requisição antes de interpretar a
pergunta ou consultar dados. O serviço reconstrói o escopo canônico diretamente
do banco e recusa snapshots forjados, desatualizados ou pertencentes a outra
identidade. A interpretação da linguagem pode restringir a consulta, mas nunca
ampliá-la.

O endpoint web passa `request.tenant_scope` explicitamente. Os fluxos filhos de
Planning e Inventory Portal também exigem esse mesmo contrato. O interpretador
semântico externo recebe somente o necessário para classificar intenção e
filtros; ele não escolhe empresas, Bases ou privilégios e não substitui as
policies locais.

## Matriz validada

| Perfil | Resultado para a mesma pergunta sobre equipamentos |
| --- | --- |
| Superuser | Todas as empresas da plataforma |
| Admin Inventory Brasil | Inventory Brasil e somente LATAM/OXXO autorizadas por relacionamento e capability da Tory |
| Admin Inventory LATAM | Somente Inventory LATAM |
| Admin OXXO | Somente OXXO |
| Gestor | Somente as Bases vinculadas ao perfil |
| Operador | Somente as Bases vinculadas ao perfil |

Inventory Brasil, Inventory LATAM e OXXO não são reconhecidas por nomes fixos.
O acesso especial do Admin Inventory Brasil continua dependendo de relações e
capabilities persistidas. O caminho inverso não é criado automaticamente e uma
empresa sem relacionamento, como a empresa adversarial usada nos testes, não é
exposta nem mesmo por contexto reapresentado à conversa.

## Consultas protegidas

- equipamentos e Bases usam o queryset seguro e a capability `TORY:VISUALIZAR`;
- transferências e empréstimos usam `TenantOperationPolicy`;
- cotações, pesquisas de preço e solicitações usam `InsumosTenantPolicy`;
- grupos e nomes de Bases são reconhecidos apenas dentro do tenant primário ou
  das Bases efetivamente autorizadas;
- resultados do Inventory Portal são reconciliados com inventários locais já
  filtrados pelo Tenant Scope;
- eventos do Planning continuam derivados apenas das Bases locais autorizadas;
- somente `is_superuser` concede escopo de plataforma; `Admin` e `is_staff` não
  concedem acesso global.

## Testes de segurança

Os testes adversariais verificam:

- a mesma pergunta para Superuser, Admin Inventory Brasil, Admin LATAM, Admin
  OXXO, Gestor e Operador;
- consulta direta a uma empresa relacionada e autorizada;
- ausência de empresa não relacionada em respostas e em contexto reapresentado;
- rejeição de Tenant Scope pertencente a outro usuário;
- rejeição de escopo de plataforma forjado por Admin de tenant;
- isolamento de preços, solicitações e contagens de transferências.

Validações executadas:

- matriz consolidada Tory/Planning/Portal/auditorias: 95 testes aprovados;
- regressão completa de `integracao.tests`: 69 testes aprovados;
- `manage.py check`: sem problemas;
- `makemigrations --check --dry-run`: nenhuma alteração pendente;
- `git diff --check`: nenhuma inconsistência de whitespace.

## Compatibilidade

Chamadas internas legadas ao serviço raiz sem um snapshot explícito continuam
funcionando somente porque o serviço reconstrói o Tenant Scope canônico naquele
momento. Essa compatibilidade não permite ampliar o escopo. Integrações filhas e
o endpoint web exigem a passagem explícita.

Não houve migration nesta etapa e nenhuma senha foi modificada. O acesso da
interface permanece conforme as permissões de perfil já definidas; o cenário de
Operador foi validado diretamente no serviço para provar que, quando usado por
um fluxo autorizado, o backend nunca ultrapassa suas Bases.

## Limite da etapa

A Etapa 20 termina com o contrato de escopo, as correções de consulta, a matriz
por perfil, os testes adversariais e esta documentação. Nenhuma implementação da
Etapa 21 foi iniciada.
