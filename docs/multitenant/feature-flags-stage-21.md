# Etapa 21 — Feature Flags por Empresa

## Estado: concluída

A plataforma passa a possuir um catálogo explícito de módulos e uma
configuração independente por empresa. Esta etapa cria a estrutura e a API
central; o bloqueio de URLs, menus, APIs, AJAX e Tory pertence à Etapa 22 e não
foi antecipado.

## Estrutura

### `Modulo`

Representa um recurso disponibilizado pela plataforma. O código é técnico,
estável, único e limitado ao catálogo conhecido. O módulo também pode ser
desativado globalmente sem apagar as configurações das empresas.

Catálogo inicial:

- `estoque`;
- `equipamentos`;
- `sick`;
- `transferencias`;
- `emprestimos`;
- `insumos`;
- `checklist`;
- `chamados`;
- `ordens_servico`;
- `catalogo`;
- `tory`.

### `ModuloEmpresa`

Relaciona uma empresa a um módulo e registra:

- estado habilitado/desabilitado;
- Superuser responsável pela última configuração feita pela API;
- datas de criação e atualização.

Cada par empresa/módulo é único. A exclusão de um módulo configurado é
protegida; o fluxo correto é desativá-lo.

## API central

`TenantFeatureService` disponibiliza:

- `has_feature(tenant, codigo)` para verificar o estado efetivo;
- `enabled_features(tenant)` para obter os códigos efetivamente habilitados;
- `configure(...)` para habilitar ou desabilitar um módulo em uma empresa;
- `provision_defaults(tenant)` para completar configurações ausentes sem
  sobrescrever decisões já existentes.

Também é possível consultar `empresa.has_feature(codigo)`.

As consultas falham de forma fechada: empresa inválida/inativa, módulo global
inativo, código desconhecido ou vínculo ausente resultam em módulo não
habilitado. Somente `actor.is_superuser` pode alterar configurações pela API;
Admin de tenant não recebe esse poder.

## Compatibilidade e backfill

A migration cria os 11 módulos e habilita todos para todas as empresas já
existentes. Empresas novas recebem os módulos ativos habilitados no momento da
criação. Isso mantém o comportamento funcional atual até que o Superuser faça
uma escolha explícita.

O provisionamento é idempotente e não reabilita uma configuração que tenha
sido desativada. Não há regra baseada em nome de empresa, username ou ID fixo.

Auditoria do banco de desenvolvimento após a migration:

- 11 módulos cadastrados;
- 4 empresas existentes;
- 44 configurações empresa/módulo;
- nenhuma empresa com catálogo incompleto;
- todos os módulos preservados como habilitados;
- somente o usuário `admin` permanece Superuser.

Nenhuma senha foi modificada.

## Migration

- `estoque.0050_modulos_por_empresa`: cria `Modulo` e `ModuloEmpresa`, popula o
  catálogo inicial e realiza o backfill idempotente das empresas existentes.

## Validação

- migration completa executada desde um banco de testes vazio: aprovada;
- testes direcionados de feature flags, Empresa, Tenant Scope, contexto,
  policies e contratos: 48 aprovados;
- testes específicos da Etapa 21: 8 aprovados dentro da regressão direcionada;
- regressão completa do app `estoque`: 281 testes executados; 7 falhas e 7
  erros legados reproduzidos em SICK, empréstimos, documentação, exportação,
  UI e cadastro de usuários, sem falha nos modelos, migration ou API da Etapa
  21;
- `manage.py check`: sem problemas;
- `makemigrations --check --dry-run`: nenhuma alteração pendente;
- `git diff --check`: nenhuma inconsistência de whitespace.

## Limite da etapa

Nenhum menu foi ocultado e nenhum endpoint foi bloqueado com base nas novas
flags nesta etapa. Assim, desabilitar uma configuração agora prepara o estado
do tenant, mas a aplicação obrigatória desse estado em todos os pontos de
entrada será feita somente na Etapa 22.
