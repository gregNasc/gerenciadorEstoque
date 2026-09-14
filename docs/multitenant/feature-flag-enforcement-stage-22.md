# Etapa 22 — Aplicação de Feature Flags no backend e na UI

## Estado: concluída

Módulos desabilitados por empresa deixam de aparecer na navegação e passam a
ser bloqueados no servidor. A proteção não depende do HTML: tentativas por URL
direta, API, AJAX, WebSocket ou Tory são rejeitadas antes de acessar a regra de
negócio do domínio desativado.

## Backend HTTP

`TenantFeatureRoutePolicy` mantém o mapeamento central entre namespaces/rotas
e os 11 módulos do catálogo. Rotas específicas prevalecem sobre a regra do
namespace, permitindo, por exemplo, separar checklists e equipamentos das
demais páginas de insumos.

`TenantFeatureMiddleware`, executado depois da montagem do contexto do tenant,
consulta o módulo requerido para a rota resolvida e responde com HTTP 403
quando ele não está habilitado para a empresa primária da requisição. A regra:

- falha de forma fechada para usuários sem empresa ou configuração válida;
- é aplicada antes dos middlewares operacionais mais específicos;
- preserva o bypass exclusivo do Superuser da plataforma;
- não altera as políticas existentes de empresa, grupo corporativo ou base.

Namespaces com endpoints sem nome também são protegidos, o que inclui APIs que
não poderiam ser cobertas apenas por uma lista de nomes de URL.

## Interface

O contexto global dos templates publica somente o conjunto de módulos
efetivamente habilitados e calcula uma página inicial compatível com esse
conjunto. A navegação principal agora condiciona:

- dashboard de ativos;
- estoque de equipamentos e insumos;
- checklists;
- chamados;
- transferências, solicitações e empréstimos;
- SICK;
- cadastros;
- indicadores de saúde e valores;
- widget e arquivos JavaScript do Tory.

Os contadores de notificações de transferências, empréstimos e chamados também
deixam de consultar e contabilizar domínios desabilitados. Assim, um módulo
oculto não influencia o total exibido em outro ponto da interface.

## Tory

O assistente aplica duas verificações independentes:

1. o módulo `tory` precisa estar habilitado para que o assistente responda;
2. depois de interpretar a pergunta, o módulo do domínio consultado também
   precisa estar habilitado.

Logo, habilitar Tory não cria um caminho indireto para consultar equipamentos,
estoque, transferências, insumos ou outro recurso desativado.

## WebSocket de chamados

Os canais de presença e chat validam o módulo `chamados` durante a conexão. Uma
empresa com chamados desabilitados recebe fechamento com código 4403, mesmo que
o usuário tente conectar diretamente ao endpoint WebSocket.

## Compatibilidade e isolamento

Todas as 44 configurações existentes permanecem habilitadas, portanto a
aplicação mantém o comportamento anterior até que o Superuser altere uma flag.
Desabilitar um módulo em uma empresa não afeta outra empresa nem amplia o
escopo entre Inventory Brasil, Inventory LATAM, OXXO ou empresas independentes.

O catálogo é garantido de forma idempotente após migrations e na criação de
empresas. Esse provisionamento apenas cria registros ausentes: uma decisão já
desabilitada nunca é reativada automaticamente.

Nenhuma senha foi modificada e nenhum novo Superuser foi criado no banco de
desenvolvimento. Somente o usuário `admin` permanece Superuser.

## Migration

Esta etapa não altera o schema. A migration da estrutura de feature flags
continua sendo `estoque.0050_modulos_por_empresa`, criada na Etapa 21.

## Validação

- 14 testes específicos da Etapa 22 aprovados;
- regressão combinada de feature flags, Tory, portal, planejamento, APIs e
  auditoria: 116 testes aprovados;
- regressão ampliada de escopo, contexto, policies, contratos e feature flags
  multi-tenant: 58 testes aprovados;
- `manage.py check`: sem problemas;
- `makemigrations --check --dry-run`: nenhuma alteração pendente;
- `git diff --check`: nenhuma inconsistência de whitespace.

## Limite da etapa

A interface de configuração administrativa das flags pertence à Etapa 23 e
não foi antecipada. Nesta etapa, a configuração continua disponível pela API
central restrita ao Superuser.
