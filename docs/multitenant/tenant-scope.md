# Etapa 9 — Serviço central de Tenant Scope

Data do checkpoint: 2026-09-05.

## Objetivo

Fornecer uma API única e fechada por padrão para resolver empresas visíveis e
administráveis por usuário, sem migrar ainda os QuerySets dos módulos de
negócio.

Uso:

```python
scope = TenantScope.for_user(user)

scope.primary_company
scope.visible_companies()
scope.can_view_company(empresa)
scope.can_manage_company(empresa)
```

O middleware constrói o serviço uma única vez por requisição e o expõe em
`request.tenant_scope`. O snapshot bruto que alimenta a resolução fica em
`request.tenant_context`.

## Regras implementadas

| Identidade | Empresas visíveis | Empresas administráveis |
|---|---|---|
| Anônimo | nenhuma | nenhuma |
| Usuário sem Perfil | nenhuma | nenhuma |
| Admin sem Empresa | nenhuma | nenhuma |
| Admin comum | principal + relações explicitamente resolvidas | somente principal |
| Gestor/Operador | principal + relações explicitamente resolvidas | nenhuma pela API de administração de Empresa |
| Superuser | todas | todas |

O escopo global é concedido exclusivamente por `user.is_superuser`. `is_staff`,
role Admin, grupos funcionais, username e nomes ou IDs fixos de Empresa não
concedem acesso global.

`can_manage_company()` representa administração do tenant, não ações
operacionais sobre Bases. As regras operacionais continuam em suas policies e
serão migradas por domínio nas etapas posteriores.

## Relacionamentos adicionais

O serviço consome `related_tenant_ids` somente quando eles fazem parte de um
`TenantRequestContext` da mesma identidade. Um contexto pertencente a outro
usuário é descartado integralmente, produzindo escopo vazio.

Relacionamentos adicionais ampliam visibilidade, mas não escrita. Escrita
cross-tenant dependerá de capabilities explícitas no relacionamento previsto
na Etapa 10.

Foi criado um contrato automatizado que resolve explicitamente:

```text
Inventory Brasil -> Inventory LATAM
Inventory Brasil -> OXXO
```

e confirma:

- exatamente essas três empresas ficam visíveis para o Admin de Inventory
  Brasil;
- uma empresa não relacionada permanece invisível;
- Admin LATAM vê somente LATAM sem relacionamento inverso;
- Admin OXXO vê somente OXXO sem relacionamento inverso.

O teste usa referências persistidas dos próprios objetos de teste. O runtime
não procura os nomes “Inventory Brasil”, “Inventory LATAM” ou “OXXO”. A fonte
persistida desses relacionamentos será criada na Etapa 10 e populada na Etapa
11. Até lá, os módulos continuam com o comportamento legado para não interromper
o acesso organizacional existente.

## Superuser

Para Superuser, `is_platform_scope=True` é a condição explícita que permite
`visible_companies()` e `can_manage_company()` atravessarem tenants. O
Superuser pode continuar sem Empresa principal.

A consulta `Empresa.objects.all()` existe somente nesse ramo explícito de
plataforma. Ela não é usada como fallback para contexto ausente ou erro de
banco.

## Falha fechada

- ausência de autenticação gera escopo vazio;
- ausência de Perfil gera escopo vazio;
- ausência de Empresa gera escopo vazio;
- falha de banco ao carregar Perfil gera contexto sem tenant;
- contexto de outro usuário é rejeitado;
- referência de Empresa nula ou inválida é negada.

## Integração com o middleware

O `EmpresaMiddleware` mantém:

```python
request.empresa is request.tenant
```

e adiciona:

```python
request.tenant_context
request.tenant_scope
```

Não há segunda consulta de Perfil na requisição normal: o serviço recebe o
snapshot já carregado pelo middleware.

## Arquivos

- `estoque/tenant_scope.py`: resolução central do escopo;
- `estoque/tenant_context.py`: identidade e role no snapshot;
- `estoque/middleware.py`: exposição do serviço na requisição;
- `estoque/test_tenant_scope.py`: contratos do serviço;
- `estoque/test_tenant_context.py`: integração do middleware.

## Migrations

Nenhuma.

## Testes

Testes direcionados:

```powershell
python manage.py test estoque.test_tenant_scope estoque.test_tenant_context --keepdb -v 1
```

Resultado: 17 testes aprovados.

Regressão combinada de identidade e contratos multi-tenant: 48 testes
executados, 41 aprovados e 7 falhas esperadas já documentadas; suíte OK.

Validações estruturais:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
```

Resultado: nenhuma inconsistência e nenhuma alteração de schema pendente.

## Compatibilidade e limites desta etapa

- nenhum QuerySet de domínio foi migrado para o serviço;
- nenhuma permissão existente foi removida;
- o acesso legado Inventory Brasil/LATAM/OXXO permanece operacional;
- nenhuma senha, conta ou dado persistido foi alterado;
- relacionamentos persistidos pertencem à Etapa 10;
- a migração da regra organizacional para esses relacionamentos pertence à
  Etapa 11.

## Próxima etapa

Etapa 10 — Model de relacionamento entre empresas.
