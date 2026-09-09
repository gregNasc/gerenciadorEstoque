# Etapa 13 — Isolamento de Equipamentos e Estoque

Data do checkpoint: 2026-09-07.

## Objetivo

Aplicar o `TenantScope` ao domínio de Equipamentos e Estoque em todos os pontos
de leitura e alteração desta etapa, impedindo que IDs ou filtros enviados
manualmente atravessem empresas.

## Fonte única de escopo

`estoque.security` passou a fornecer seletores centrais para:

```python
secure_queryset(...)
secure_base_queryset(...)
secure_company_queryset(...)
secure_history_queryset(...)
```

As regras são:

- Superuser mantém escopo global explícito;
- Admin recebe a Empresa principal e somente as empresas adicionais
  selecionadas no Perfil;
- uma empresa adicional só entra no estoque quando o relacionamento possui a
  capability exata de Equipamentos para a ação;
- Gestor e Operador continuam limitados às Bases vinculadas;
- Perfil ausente, Empresa ausente ou escopo vazio retornam QuerySet vazio;
- a ocultação temporária de equipamentos sob auditoria continua ativa,
  inclusive para Admin e Superuser.

A Empresa principal não depende de capability de relacionamento. Em empresa
adicional, visualizar, criar, editar e movimentar são decisões distintas.

## Superfícies protegidas

Foram migrados para os seletores centrais:

- dashboard principal e KPIs;
- listagem de estoque e filtros por Empresa, Base, produto e finalidade;
- cadastro e validação de Base no formulário;
- edição de equipamento e troca de Base;
- detalhes de produto e equipamento;
- APIs de KPIs, Bases, regionais e equipamentos disponíveis;
- busca avançada;
- histórico, detalhe e modal de histórico;
- exports Excel e PDF;
- serviço de estoque agregado por produto;
- consultas de equipamentos reutilizadas por Chamados e pelo assistente.

O catálogo `Produto` permanece corporativo e compartilhado; o isolamento é
aplicado aos equipamentos físicos, suas Bases e seus históricos.

## Proteção contra alteração manual de IDs

Parâmetros de Empresa, Base, equipamento e histórico são resolvidos dentro do
QuerySet autorizado. Uma referência existente em outra empresa retorna 404 e
não revela o objeto.

Também foram validados:

- POST de cadastro com Base externa rejeitado;
- filtro de Empresa externa rejeitado;
- AJAX com Base externa rejeitado;
- Admin sem a empresa adicional selecionada não vê seus equipamentos;
- empresa selecionada sem `EQUIPAMENTOS:VISUALIZAR` não entra no resultado;
- edição em empresa relacionada exige `EQUIPAMENTOS:EDITAR`;
- export não contém serial ou patrimônio de empresa externa.

## Contrato multi-tenant ativado

Os sete cenários anteriormente marcados como falhas esperadas em
`test_multitenant_contract.py` passaram a ser contratos ativos:

- Superuser atravessa tenants;
- Admin comum não atravessa empresas;
- Inventory Brasil alcança somente LATAM/OXXO selecionadas e autorizadas;
- LATAM e OXXO não recebem acesso inverso;
- Gestor e Operador permanecem restritos.

Fixtures legados de equipamento também foram alinhados à regra já consolidada
de que um Admin de tenant deve possuir Empresa principal.

## Arquivos principais

- `estoque/security.py`;
- `estoque/utils.py`;
- `estoque/forms.py`;
- `estoque/views.py`;
- `estoque/services/estoque_service.py`;
- `estoque/test_inventory_tenant_isolation.py`;
- `estoque/test_multitenant_contract.py`;
- `estoque/test_equipamentos_sick.py`.

## Migrations

Nenhuma migration nova. A etapa consome o schema e os relacionamentos das
Etapas 10, 11 e do ajuste multiempresa.

## Validação

Testes essenciais da Etapa 13: 17 aprovados (8 testes específicos de
isolamento e 9 contratos multi-tenant ativos).

Regressão das telas e serviços afetados, incluindo Estoque, Equipamentos, SICK,
Auditorias e Chamados: 127 testes aprovados.

```powershell
python manage.py test estoque.test_inventory_tenant_isolation estoque.test_multitenant_contract --keepdb -v 2
python manage.py test estoque.test_inventory_tenant_isolation estoque.test_multitenant_contract estoque.test_index_filters estoque.test_equipamentos_sick auditorias.tests.test_core chamados.tests --keepdb -v 1
python manage.py check
python manage.py makemigrations --check --dry-run
```

Nenhuma senha, flag de conta ou vínculo de Superuser foi alterado.

## Limite da etapa

Fluxos completos de SICK, Transferências e Empréstimos pertencem à Etapa 14.
Esta etapa protegeu as referências de equipamento usadas pelas superfícies de
Estoque sem antecipar a conversão integral desses três domínios.

## Próxima etapa

Etapa 14 — SICK, Transferências e Empréstimos.

