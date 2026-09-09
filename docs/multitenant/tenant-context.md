# Etapa 8 — Novo Tenant Context

Data do checkpoint: 2026-09-05.

## Objetivo

Centralizar o contexto tenant-aware de cada requisição sem antecipar a política
de autorização da Etapa 9 nem os relacionamentos persistidos das Etapas 10 e
11.

O `EmpresaMiddleware` agora disponibiliza:

```python
request.empresa       # alias legado
request.tenant        # Empresa principal ou None
request.tenant_context # TenantRequestContext imutável
request.tenant_scope   # TenantScope resolvido desde a Etapa 9
```

`request.empresa` e `request.tenant` apontam para o mesmo objeto. Assim, os
consumidores existentes continuam funcionando enquanto o código novo pode usar
a nomenclatura de tenant.

## Snapshot do contexto

`TenantRequestContext` contém somente fatos resolvidos para a requisição:

- `primary_tenant`: Empresa principal do Perfil;
- `primary_tenant_id`: ID da Empresa principal;
- `related_tenant_ids`: IDs de relacionamentos adicionais fornecidos
  explicitamente por uma camada confiável;
- `tenant_ids`: união do tenant principal com os relacionados;
- `user_id`: identidade dona do snapshot;
- `profile_id`: Perfil que originou o contexto;
- `profile_role`: role lido do Perfil;
- `is_platform_superuser`: informa se o usuário é Superuser;
- `has_fixed_tenant` e `is_empty`: propriedades de estado.

O objeto é imutável e não possui métodos como `can_view`, `can_write` ou
`can_manage`. O middleware descreve o contexto, mas não decide permissões de
leitura ou escrita.

## Comportamento por identidade

| Identidade | `request.tenant` | `tenant_scope.tenant_ids` | Marca de plataforma |
|---|---|---|---:|
| Anônimo | `None` | vazio | não |
| Usuário sem Perfil | `None` | vazio | conforme `is_superuser` |
| Admin legado sem Empresa | `None` | vazio | não |
| Usuário com Empresa | Empresa principal | somente a principal nesta etapa | conforme `is_superuser` |
| Superuser sem Empresa | `None` | vazio | sim |
| Erro de banco ao resolver Perfil | `None` | vazio | conforme `is_superuser` |

Não existe fallback para `Empresa.objects.all()`, primeira Empresa do banco,
nome de empresa, username ou ID fixo. Ausência de Empresa sempre produz escopo
vazio, nunca acesso global implícito.

## Relacionamentos adicionais

O snapshot já consegue representar `related_tenant_ids`, mas o middleware não
os inventa nem promove escopos funcionais, como `empresas_escopo_compras`, a
acesso geral. A fonte central de empresas acessíveis será criada na Etapa 9; o
model persistido e a regra Inventory Brasil → Inventory LATAM/OXXO pertencem às
Etapas 10 e 11.

Até lá, o acesso global legado dos Admins não foi removido nesta etapa. Isso
preserva o comportamento necessário de Inventory Brasil, Inventory LATAM e
OXXO enquanto os contratos de isolamento ainda permanecem marcados como falhas
esperadas.

## Superuser

`is_platform_superuser=True` é metadado, não autorização concedida pelo
middleware. Um Superuser pode não ter tenant principal e, nesse caso,
`tenant_ids` continua vazio. Policies e services deverão usar
`request.user.is_superuser` explicitamente quando a operação global for
permitida.

A conta `admin` continua sendo o único Superuser do banco local. Esta etapa não
altera contas, vínculos ou senhas.

## Falha fechada

Se a consulta do Perfil falhar com `DatabaseError`, os três atributos ainda são
definidos, porém com tenant ausente e escopo vazio. Dessa forma, indisponibilidade
ou erro de resolução nunca amplia o acesso.

## Arquivos

- `estoque/tenant_context.py`: snapshot imutável do contexto;
- `estoque/middleware.py`: construção e exposição dos atributos na requisição;
- `estoque/test_tenant_context.py`: testes direcionados.

## Migrations

Nenhuma. A etapa altera somente a camada de requisição.

## Testes

Testes direcionados do Tenant Context: 7 aprovados.

Regressão combinada executada:

```powershell
python manage.py test estoque.test_tenant_context estoque.test_admin_company estoque.test_audit_tenant_profiles estoque.test_multitenant_contract estoque.test_user_access_profiles --keepdb -v 1
```

Resultado: 38 testes executados, 31 aprovados e 7 falhas esperadas dos contratos
que serão ativados progressivamente; suíte OK.

Validações estruturais:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
```

## Compatibilidade

- ordem do middleware: preservada;
- `request.empresa`: preservado;
- login e perfis existentes: preservados;
- regras de escrita: não alteradas;
- regra organizacional Inventory Brasil/LATAM/OXXO: preservada no estado legado;
- dados e senhas: não alterados.

## Próxima etapa

Etapa 9 — Serviço central de Tenant Scope.
