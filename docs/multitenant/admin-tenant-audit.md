# Auditoria e backfill de tenant dos Admins

## Status

- Etapa: 7 — Diagnóstico e backfill de Admins
- Estado: concluída e validada
- Data: 2026-09-05
- Alteração de schema: nenhuma
- Alteração de senha: nenhuma
- Backfills aplicados na execução inicial: 0

## Comando

O diagnóstico é somente leitura por padrão:

```powershell
python manage.py audit_tenant_profiles
```

É possível restringir a uma ou mais contas:

```powershell
python manage.py audit_tenant_profiles --username usuario.a --username usuario.b
```

O backfill seguro precisa ser solicitado explicitamente:

```powershell
python manage.py audit_tenant_profiles --apply
```

O relatório mostra, para cada perfil Admin:

- usuário, role, estado ativo, `is_staff` e `is_superuser`;
- empresa atual;
- grupos Django;
- regionais, bases de checklist, empresas e bases do escopo de compras;
- evidências configuradas por empresa;
- sinais de atividade operacional por empresa e quantidade de registros;
- decisão, possível tenant candidato e justificativa.

## Política de decisão

O comando não usa username, nome, e-mail ou semelhança textual para inferir
tenant. Também não considera atividade histórica isolada uma autorização.

| Decisão | Significado | `--apply` altera? |
|---|---|---:|
| `ASSOCIADO` | O perfil já possui empresa | não |
| `SUPERUSER_PLATAFORMA` | Exceção global de plataforma | não |
| `ELEGIVEL` | Exatamente uma empresa configurada explicitamente e nenhum conflito operacional | sim |
| `PROVAVEL_REVISAO_MANUAL` | Um único sinal operacional, mas nenhuma configuração explícita | não |
| `AMBIGUO` | Mais de uma empresa ou conflito entre configuração e histórico | não |
| `SEM_EVIDENCIA` | Nenhuma evidência tenant-aware | não |

As fontes explícitas são `regionais`, `bases_checklist`,
`empresas_escopo_compras` e `bases_escopo_compras`. Chamados, inventários,
insumos, empréstimos, solicitações, transferências, compras, ordens de serviço
e campanhas de auditoria são exibidos somente como sinais operacionais.

Antes de atualizar, o `--apply` bloqueia novamente a linha do perfil e refaz a
classificação dentro de uma transação. Isso evita aplicar uma decisão que tenha
ficado obsoleta entre a auditoria e a escrita. A execução é idempotente.

## Exceção da conta `admin`

A conta `admin` continua sendo o único superuser e é classificada como
`SUPERUSER_PLATAFORMA`. Seus registros operacionais abrangem Inventory Brasil,
Inventory Latam e OXXO, coerentemente com o acesso global de plataforma, mas
nenhum deles é usado para preencher `Perfil.empresa`. Senha e flags da conta
não são alteradas pelo comando.

## Resultado da execução inicial

Em 2026-09-05, a auditoria encontrou:

| Classificação | Quantidade |
|---|---:|
| Admin já associado | 1 |
| Superuser de plataforma | 1 |
| Elegível para backfill | 0 |
| Provável, com revisão manual | 0 |
| Ambíguo | 0 |
| Sem evidência | 5 |

O Admin já associado é `jose.barboza`, vinculado a Inventory Brasil. As cinco
contas sem evidência permaneceram intactas. A execução real com `--apply`
confirmou `BACKFILLS_APLICADOS: 0`.

## Validação automatizada

Os testes em `estoque/test_audit_tenant_profiles.py` cobrem:

- modo padrão sem escrita;
- backfill inequívoco e idempotência;
- proteção absoluta do superuser;
- atividade operacional isolada exigindo revisão manual;
- configurações explícitas conflitantes;
- conflito entre configuração e histórico;
- presença de role, grupos e bases no relatório.

Resultado: 7 testes aprovados e `manage.py check` sem problemas.
