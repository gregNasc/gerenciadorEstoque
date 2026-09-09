# Etapa 10 — Relacionamentos entre empresas

Data do checkpoint: 2026-09-05.

## Objetivo

Persistir relacionamentos direcionais entre tenants e suas capabilities sem
usar nomes, usernames, IDs fixos ou um booleano global de acesso.

## Models

### `RelacionamentoEmpresa`

Representa uma relação unidirecional:

```text
empresa_origem -> empresa_destino
```

Campos:

- `empresa_origem`;
- `empresa_destino`;
- `ativo`;
- `criado_por`;
- `criado_em`;
- `atualizado_em`.

Invariantes no banco:

- origem e destino precisam ser diferentes;
- cada par origem/destino pode existir uma única vez;
- criar A → B não cria B → A.

### `CapacidadeRelacionamentoEmpresa`

Cada permissão é uma combinação explícita de:

```text
relacionamento + recurso + ação
```

O registro possui `ativo`, autoria e timestamps próprios. Uma capability
desativada não concede acesso. A mesma combinação não pode ser duplicada.

Recursos disponíveis:

- operação do tenant;
- equipamentos e estoque;
- SICK, transferências e empréstimos;
- insumos, checklists e inventários;
- chamados;
- compras e catálogo;
- ordens de serviço;
- auditorias;
- documentação;
- integrações;
- Tory;
- usuários.

Ações disponíveis:

- visualizar;
- criar;
- editar;
- movimentar;
- atender;
- aprovar;
- exportar;
- administrar.

Nem toda combinação recurso/ação precisa ser usada. As policies de cada domínio
consumirão apenas as combinações coerentes com seus fluxos.

## Integração com `TenantScope`

Para usuários com role Admin, `TenantScope` carrega somente capabilities:

- pertencentes a uma relação cuja origem é a Empresa principal;
- com relacionamento ativo;
- com capability ativa.

Uma relação sem capabilities ativas não amplia o escopo. O destino de qualquer
capability ativa passa a fazer parte de `visible_companies()`, enquanto a ação
específica pode ser consultada por:

```python
scope.has_related_capability(empresa, recurso, acao)
```

`can_manage_company()` só inclui um tenant relacionado quando existe a
capability explícita `OPERACAO:ADMINISTRAR`. Administrar um recurso isolado,
como `CHAMADOS:ADMINISTRAR`, não se transforma em administração geral do tenant.

Gestores e Operadores não herdam relacionamentos entre Empresas. Eles continuam
limitados por Empresa e Bases atribuídas ao Perfil. Superusers continuam globais
por `user.is_superuser`, independentemente dos relacionamentos.

## Administração

Os dois models foram registrados no Django Admin, com capabilities editáveis
também como inline do relacionamento. Visualizar, criar, alterar ou excluir
essas configurações exige `request.user.is_superuser`; ser `is_staff`, Admin de
tenant ou possuir permissões Django isoladas não é suficiente.

Autoria e timestamps são somente leitura no painel. Novos registros criados no
painel recebem automaticamente o Superuser responsável.

## Estado inicial

A migration cria somente a estrutura. Nenhum relacionamento ou capability é
inserido nesta etapa.

Os registros Inventory Brasil → Inventory LATAM e Inventory Brasil → OXXO serão
criados e validados na Etapa 11, com falha explícita se os tenants não puderem
ser identificados de forma inequívoca durante o processo de migração.

## Migration

`estoque/migrations/0044_relacionamentoempresa_and_more.py`

Operações:

- criação de `RelacionamentoEmpresa`;
- criação de `CapacidadeRelacionamentoEmpresa`;
- constraint de par direcional único;
- constraint impedindo autorrelacionamento;
- constraint de capability única;
- índice para capabilities ativas por recurso e ação.

A migration é aditiva, não altera tabelas operacionais e não remove dados.

## Testes

Testes direcionados cobrem:

- direção e ausência de relação inversa automática;
- autorrelacionamento rejeitado no model e no banco;
- unicidade do par origem/destino;
- unicidade de capability;
- catálogo de recursos e ações;
- relação/capability inativa sem concessão;
- relação sem capability sem concessão;
- carregamento pelo `TenantScope` somente para Admin;
- Gestor sem herança do relacionamento;
- administração relacionada somente com `OPERACAO:ADMINISTRAR`;
- painel restrito a Superuser.

Comando direcionado:

```powershell
python manage.py test estoque.test_company_relationships estoque.test_tenant_scope estoque.test_tenant_context --keepdb -v 2
```

Resultado: 30 testes aprovados.

Regressão combinada de identidade, contexto, escopo e contratos multi-tenant:
61 testes executados, 54 aprovados e 7 falhas esperadas já documentadas; suíte
OK.

Validações estruturais:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
```

Resultado: nenhuma inconsistência e nenhuma alteração de schema pendente. A
migration 0044 foi aplicada com sucesso ao banco local. Após a aplicação, as
novas tabelas continham zero relacionamentos e zero capabilities, conforme o
limite desta etapa.

## Compatibilidade

- nenhum relacionamento real criado nesta etapa;
- comportamento legado dos módulos preservado;
- nenhuma senha ou perfil alterado;
- somente `admin` permanece Superuser;
- nenhuma policy de domínio passou a aceitar escrita cross-tenant;
- nenhuma regra depende do nome das Empresas em runtime.

## Próxima etapa

Etapa 11 — Migrar a regra Inventory Brasil → Inventory LATAM/OXXO.
