# Release Gate R8 — Indicadores, consumo e sugestões

**Data:** 05/11/2026
**Status local:** APROVADO

## Escopo concluído

- painel **Planejamento de consumo** acessível pela navegação de Insumos;
- filtros por empresa, Base, período, categoria e busca textual;
- empresa principal selecionada na primeira carga;
- separação explícita entre Solicitado, Atendido e Consumido;
- estoque disponível descontando reservas;
- última solicitação, quantidade usual e intervalo típico;
- mediana usada nas métricas sujeitas a valores extremos;
- tendência e demanda anual estimada;
- cobertura aproximada e referência para 30 dias;
- sugestões informativas, sem criação ou preenchimento automático de pedido;
- exportação Excel com os mesmos filtros;
- interface em português e espanhol;
- nenhum preço, custo ou valor financeiro no painel ou na exportação.

## Fontes

| Indicador | Fonte oficial |
|---|---|
| Solicitado | `ItemSolicitacaoInsumo.quantidade` |
| Atendido | `ItemSolicitacaoInsumo.quantidade_atendida` |
| Consumido | `ConsumoInsumo.quantidade` |
| Estoque | `SaldoInsumoBase` |
| Pendências | `SolicitacaoInsumo` em estados abertos |

## Permissões

Permitidos:

- Superuser;
- Admin;
- Compras;
- Planejamento;
- Executivo.

Gestor ou Operador sem perfil funcional recebe 403. Empresa e Base fora do
escopo também recebem 403. A lista de empresas contém somente organizações
autorizadas e ativas.

## Desempenho

- consultas agregadas por fonte;
- nenhuma consulta por item renderizado;
- intervalo temporal preserva índices de data;
- catálogo carregado em lote;
- Bases autorizadas calculadas uma vez e reutilizadas;
- teste automatizado limita o total de consultas;
- nenhuma biblioteca JavaScript externa é carregada pelo painel.

## Testes finais

Regressão integrada:

```text
insumos.tests
insumos.test_indicadores_planejamento_r8
estoque.test_user_access_profiles
estoque.test_tenant_dashboard_categories

63 testes aprovados
```

Checks:

```text
python manage.py check
System check identified no issues.

python manage.py makemigrations --check --dry-run
No changes detected.
```

## Migrations

Nenhuma.

## Deploy

1. enviar a `main` ao repositório remoto;
2. executar o deploy normal;
3. o `build.sh` executará `migrate`, sem migration nova do R8;
4. acessar **Insumos → Planejamento de consumo**;
5. confirmar que a primeira carga usa a empresa principal;
6. comparar um item conhecido entre Solicitações, Checklists e Estoque;
7. exportar a planilha e confirmar ausência de preços;
8. testar um usuário de outra empresa e um Gestor sem perfil funcional.

## Rollback

Reverter o commit do R8 restaura o painel anterior. Não existe rollback de
banco, pois nenhuma alteração de schema ou de dados foi realizada.

## Próxima release

R9 — integração TOTVS. Não iniciar sem confirmar produto, versão, módulos,
processo atual, APIs, credenciais e ambiente de homologação.
