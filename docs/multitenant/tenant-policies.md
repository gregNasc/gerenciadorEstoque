# Etapa 12 — Decorators e policies de tenant

Data do checkpoint: 2026-09-07.

## Objetivo

Centralizar as proteções da fronteira tenant para que as views dos domínios não
repitam verificações manuais de `request.user`, Empresa e propriedade dos
objetos.

## API central

`TenantAccessPolicy` oferece operações fechadas por padrão:

```python
TenantAccessPolicy.scope_for_request(request)
TenantAccessPolicy.require_tenant(request)
TenantAccessPolicy.can_access_company(request, empresa)
TenantAccessPolicy.require_company_access(request, empresa)
TenantAccessPolicy.can_access_object(
    request,
    objeto,
    company_path='base__empresa',
)
TenantAccessPolicy.require_object_access(
    request,
    objeto,
    company_path='empresa',
)
```

Um `request.tenant_scope` só é reutilizado quando pertence ao mesmo usuário da
requisição. Escopo ausente, adulterado ou pertencente a outra identidade é
recalculado sem aproveitar seus tenants.

## Decorators

### Contexto tenant

```python
@tenant_required
def minha_view(request):
    ...
```

Exige autenticação e Empresa principal fixa. O único caso sem Empresa aceito é
o Superuser com escopo explícito de plataforma.

### Empresa identificada pela URL

```python
@tenant_company_access(company_kwarg='empresa_id')
def detalhe_empresa(request, empresa_id):
    empresa = request.tenant_company
```

Também pode exigir uma capability exata em acesso relacionado:

```python
@tenant_company_access(
    company_kwarg='empresa_id',
    resource='CHAMADOS',
    action='VISUALIZAR',
)
def chamados_empresa(request, empresa_id):
    ...
```

### Objeto pertencente ao tenant

```python
@tenant_object_access(
    Equipamento,
    company_path='regional__empresa',
    lookup_url_kwarg='equipamento_id',
)
def detalhe_equipamento(request, equipamento_id):
    equipamento = request.tenant_object
```

O objeto é carregado pelo decorator e negado quando o caminho indicado resolve
uma Empresa fora do `TenantScope`.

## Regras de decisão

- anônimo, Perfil sem Empresa e referência inválida falham fechados;
- Admin acessa a Empresa principal e somente as adicionais selecionadas;
- em Empresa relacionada, `resource` + `action` exigem capability exata;
- `manage=True` exige que a Empresa seja administrável no `TenantScope`;
- Gestor e Operador não herdam relacionamentos entre Empresas;
- somente Superuser recebe passagem global explícita;
- a policy de tenant não substitui as permissões funcionais do módulo.

Essa última separação é intencional: estar dentro da Empresa não concede, por
si só, permissão para aprovar, editar, excluir ou administrar um recurso.

## Feature flags

O exemplo conceitual `tenant_feature_required` não foi simulado com dados
inexistentes. O modelo e a API de features pertencem à Etapa 21; sua aplicação
no backend e na UI pertence à Etapa 22. Quando essas estruturas existirem, o
decorator poderá ser acrescentado sobre a mesma policy central.

## Escopo desta etapa

Esta etapa cria e valida a infraestrutura reutilizável. A migração dos
QuerySets e views de negócio começa na Etapa 13, domínio por domínio, conforme o
plano. Nenhum domínio foi convertido antecipadamente.

## Arquivos

- `estoque/tenant_policies.py`;
- `estoque/decorators.py`;
- `estoque/test_tenant_policies.py`.

## Validação

Os testes direcionados cobrem contexto fixo, Superuser, escopo adulterado,
seleção individual de LATAM/OXXO, capability exata, administração de empresa
relacionada, Gestor sem herança e bloqueio de objeto cross-tenant.

```powershell
python manage.py test estoque.test_tenant_policies estoque.test_admin_multi_company --keepdb -v 2
python manage.py check
python manage.py makemigrations --check --dry-run
```

Resultado: 17 testes aprovados, nenhuma inconsistência e nenhuma migration
pendente.

Regressão consolidada das Etapas 6–12: 68 testes aprovados.

## Próxima etapa

Etapa 13 — Equipamentos e Estoque.
