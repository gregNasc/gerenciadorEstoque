# Etapa 11 — Inventory Brasil → Inventory LATAM/OXXO

Data do checkpoint: 2026-09-07.

## Objetivo

Migrar a exceção organizacional histórica para relacionamentos persistidos,
direcionais, configuráveis e consumidos pelo `TenantScope`.

## Relacionamentos criados

```text
Inventory Brasil -> Inventory LATAM
Inventory Brasil -> OXXO
```

Não foram criados:

```text
Inventory LATAM -> Inventory Brasil
OXXO -> Inventory Brasil
```

Também não existe relacionamento com uma quarta Empresa.

## Identificação segura durante a migration

A migration localiza os três registros legados por slug e nome somente durante
o backfill. Ela não usa IDs numéricos e o runtime não contém comparação com
esses nomes.

Antes de escrever, a migration exige exatamente uma correspondência para cada
tenant e confirma que os três registros são distintos. O comportamento é:

- banco sem nenhum dos três tenants: não cria dados, permitindo instalação
  nova e vazia;
- conjunto parcial: falha explicitamente antes de escrever;
- correspondência duplicada ou ambígua: falha explicitamente antes de escrever;
- conjunto completo e inequívoco: cria ou reativa os dois relacionamentos.

## Capabilities

Cada relacionamento recebeu o preset operacional completo confirmado para o
Admin da Inventory Brasil:

- `OPERACAO:ADMINISTRAR`;
- 17 recursos de domínio;
- 8 ações por recurso.

Isso totaliza 137 capabilities ativas por relacionamento. Os recursos cobrem
equipamentos, estoque, SICK, transferências, empréstimos, insumos, checklists,
inventários, chamados, compras, catálogo, ordens de serviço, auditorias,
documentação, integrações, Tory e usuários. As ações cobrem visualizar, criar,
editar, movimentar, atender, aprovar, exportar e administrar.

As capabilities não incluem criação de tenants, edição estrutural da plataforma
ou administração dos próprios relacionamentos. Essas funções continuam
exclusivas do Superuser.

## Idempotência e preservação

A migration usa os pares origem/destino e recurso/ação como chaves naturais:

- uma nova execução não duplica relacionamentos;
- uma nova execução não duplica capabilities;
- registros obrigatórios inativos são reativados;
- autoria já existente não é sobrescrita;
- o passo reverso não apaga configuração operacional, evitando perda silenciosa
  de dados em rollback intermediário.

## Resultado no banco local

Após aplicar a migration:

| Origem | Destino | Estado | Capabilities ativas |
|---|---|---:|---:|
| Inventory Brasil | Inventory LATAM | ativo | 137 |
| Inventory Brasil | OXXO | ativo | 137 |

Relacionamentos inversos: 0.

O Admin de tenant `jose.barboza`, vinculado à Inventory Brasil, foi resolvido
pelo `TenantScope` com exatamente:

```text
inventory-brasil
inventory-latam
oxxo
```

Nenhum Perfil, role, grupo, flag de usuário ou senha foi alterado. A conta
`admin` permanece como único Superuser.

## Migration

`estoque/migrations/0045_inventory_brasil_relationships.py`

A migration é exclusivamente de dados e depende da estrutura criada em 0044.

## Testes direcionados

Os testes cobrem:

- instalação vazia;
- estado parcial recusado antes de escrita;
- identificação ambígua recusada antes de escrita;
- dois relacionamentos no sentido correto;
- ausência de relação inversa e de quarta empresa;
- 137 capabilities ativas em cada relação;
- idempotência e reativação;
- escopo exato do Admin Inventory Brasil;
- LATAM sem acesso inverso;
- integração com models e `TenantScope` da Etapa 10.

Comando:

```powershell
python manage.py test estoque.test_inventory_relationship_migration estoque.test_company_relationships estoque.test_tenant_scope --keepdb -v 2
```

Resultado: 29 testes aprovados.

Regressão consolidada das etapas de identidade, contexto, escopo,
relacionamentos e contratos multi-tenant: 67 testes executados, 60 aprovados e
7 falhas esperadas já documentadas; suíte OK.

Validações estruturais obrigatórias:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
```

Resultado: nenhuma inconsistência e nenhuma alteração de schema pendente. A
auditoria final confirmou 2 relacionamentos ativos, 274 capabilities ativas,
zero relacionamentos inversos e somente `admin` como Superuser.

## Compatibilidade e limite

Os relacionamentos já são a fonte persistida do `TenantScope`. Os QuerySets dos
módulos ainda não foram migrados para essa API; essa aplicação gradual começa
nas etapas de policies e isolamento por domínio. O comportamento legado não foi
removido nesta etapa, evitando interrupção do acesso atual.

## Próxima etapa

Etapa 12 — Decorators / policies de tenant.
