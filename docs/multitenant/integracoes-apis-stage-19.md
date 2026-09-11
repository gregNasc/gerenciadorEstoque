# Etapa 19 — Integrações e APIs

## Estado: concluída

As integrações externas, importações e exportações auditadas agora trabalham
com escopo de execução declarado. Integrações pertencentes à plataforma usam
`PLATFORM_GLOBAL` de forma explícita; operações de tenant exigem a empresa
autorizada antes da leitura, persistência ou entrega externa.

## Matriz de integrações

| Integração ou fluxo | Escopo declarado | Proteção aplicada |
| --- | --- | --- |
| Inventory Planning | Plataforma global | Sincronizações registram origem e escopo; a configuração de bindings é exclusiva do Superuser |
| Materialização do Planning | Base/empresa definida no binding | Eventos externos só se tornam inventários locais depois de um mapeamento explícito |
| Inventory Portal | Dados retornados filtrados pelo escopo local do usuário | Apenas o Superuser ignora o filtro; Admin comum não recebe inventários de empresa não autorizada |
| Pesquisa de preços | Tenant informado pelo chamador | A empresa é obrigatória e validada pela policy de edição antes de consultar e persistir resultados |
| WhatsApp de comunicados | Tenant do comunicado ou plataforma global criada por Superuser | Entregas sem escopo são ignoradas; o provedor recebe o escopo validado |
| Webhook do WhatsApp | Plataforma global | Assinatura criptográfica obrigatória e atualização somente da entrega localizada pelo identificador do provedor |
| Importação XLSX de calendário | Plataforma global | Operação exclusiva do Superuser e escopo exibido na interface e no resumo |
| Exportação XLSX de inventários | Tenant/capability `EXPORTAR` | Inventários e a aba de clientes são derivados do mesmo queryset autorizado |
| Importação legada de banco | Plataforma global | Execução recusada sem `LEGACY_IMPORT_SCOPE=PLATFORM_GLOBAL` |

Endpoints internos permanecem autenticados e usam as policies do domínio para
resolver objetos antes de responder. Endpoints técnicos de saúde não retornam
dados pertencentes a tenants.

O intérprete semântico da Tory não foi alterado nesta etapa. Seu escopo
funcional e os testes por perfil pertencem à Etapa 20; a correção preventiva do
Inventory Portal nesta etapa garante que resultados externos já sejam
reconciliados com inventários locais autorizados antes de chegar ao usuário.

## Regras consolidadas

- somente `user.is_superuser` representa acesso global;
- `is_staff` e o role `Admin` não concedem acesso global;
- Admin de tenant vê somente a própria empresa e relacionamentos/capabilities
  explicitamente configurados;
- a exceção Inventory Brasil, Inventory LATAM e OXXO continua dependente das
  relações persistidas, sem revelar outras empresas;
- Gestores e Operadores permanecem limitados às Bases autorizadas;
- integrações globais não inferem tenant por nome, username ou ID fixo;
- filtros de interface não substituem o filtro de backend;
- nenhuma senha foi modificada.

## Migração

- `integracao.0004_declarar_escopo_global_execucoes`: marca execuções históricas
  do Planning sem declaração como `PLATFORM_GLOBAL`, preservando os filtros já
  armazenados.

Auditoria após a migration no banco de desenvolvimento:

- 37 execuções históricas do Planning;
- nenhuma execução sem `kind = PLATFORM_GLOBAL` e `source`;
- somente o usuário `admin` é Superuser.

## Validação

- regressão completa de `integracao.tests`: 69 testes aprovados;
- regressão completa do app `insumos`: 55 testes aprovados;
- comunicação WhatsApp: 7 testes aprovados;
- total de testes direcionados distintos: 131 aprovados;
- migration aplicada no banco de desenvolvimento;
- `manage.py check`: sem problemas;
- `makemigrations --check --dry-run`: nenhuma alteração pendente;
- `git diff --check`: nenhuma inconsistência de whitespace.

## Compatibilidade e pendências

O comportamento operacional anterior foi preservado, exceto pelos acessos
globais implícitos que constituíam risco de vazamento. Não há pendência que
obrigue iniciar a Etapa 20 para o sistema permanecer funcional.

A Etapa 20 deverá tratar exclusivamente a Tory, garantindo que toda pergunta
receba o Tenant Scope já autorizado e comparando respostas equivalentes entre
Superuser, Admins, Gestores e Operadores.
