# Etapa 15 — Insumos e Checklists

## Estado: concluída

O primeiro bloco centraliza o escopo dos domínios de insumos, inventários e
checklists em `InsumosTenantPolicy`. Permissão funcional e escopo de dados são
decisões separadas.

## Regras já aplicadas

- Admin acessa as Bases de sua empresa principal;
- empresa adicional exige seleção no perfil e capability exata do recurso/ação;
- Gestor e Operador continuam restritos às Bases vinculadas ao perfil;
- grupo funcional não cria acesso global automático;
- perfil funcional sem tenant/Base explícitos recebe escopo vazio;
- somente Superuser mantém escopo global da plataforma;
- IDs externos de inventário, checklist e ajuste de estoque são resolvidos em
  querysets previamente filtrados;
- comunicados operacionais de checklist e ajuste não são enviados a admins de
  tenants sem vínculo.

## Escopo coberto

- estoque e saldo de insumos;
- solicitações e decisões;
- dashboards e APIs de consumo;
- listagem, detalhe, edição, impressão e exportação de checklists;
- listagem, detalhe, edição e exportação de inventários;
- seleção de Bases, equipamentos e lotes;
- ajuste de estoque;
- dashboards de saúde, custos e planejamento sincronizado;
- perfis funcionais com empresa e Bases obrigatórias, atribuíveis somente pelo
  Superuser;
- histórico operacional vinculado à Base, com migração segura dos registros
  legados identificáveis;
- serviços de movimentação, consumo e agregações protegidos por política;
- importação global restrita ao Superuser.

Históricos globais de catálogo, sem Base, permanecem exclusivos do Superuser.
Registros legados cujo tenant não possa ser determinado de forma inequívoca
também falham de modo fechado e não são exibidos a usuários comuns.

## Validação

- `manage.py check`: sem problemas;
- `makemigrations --check --dry-run`: nenhuma alteração pendente;
- 49 testes de isolamento, lifecycle de checklist, custos e gestão de usuários:
  aprovados.

Na auditoria do banco de desenvolvimento, somente `admin` permanece como
Superuser. O perfil funcional legado `victor.ribeiro` não possui empresa nem
Base e, por segurança, permanece sem escopo de dados até ser configurado pelo
Superuser no painel de usuários.
