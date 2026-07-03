# 07 — Dashboards

## Objetivo

Os dashboards representam a camada de Business Intelligence (BI) do Gerenciador de Estoque.

Seu objetivo não é apenas apresentar números, mas transformar dados operacionais em informações úteis para tomada de decisão.

Cada dashboard possui um público específico e deve responder às perguntas relevantes para aquele perfil.

---

# Princípios

Todo dashboard deve seguir os princípios abaixo.

## Responder perguntas

Um dashboard deve responder perguntas reais da operação.

Nunca existir apenas para apresentar gráficos.

---

## Atualização automática

Os dashboards devem consumir informações geradas pelos Services.

Nunca depender de atualização manual.

---

## Drill-down

Sempre que possível, um indicador deve permitir aprofundamento.

Exemplo:

```text
Custo por Grupo

↓

Bases

↓

Inventários

↓

Checklist

↓

Itens Consumidos
```

---

## Performance

Dashboards devem utilizar consultas otimizadas.

Sempre que necessário:

* annotate()
* select_related()
* prefetch_related()
* cache

---

## Padronização

Todos os dashboards devem possuir identidade visual única.

Componentes semelhantes devem ter comportamento semelhante.

---

# Dashboard Principal (Index)

## Público

Todos os usuários.

---

## Objetivo

Fornecer visão geral do parque de equipamentos.

---

## Deve responder

Quantos equipamentos existem?

Quantos estão ativos?

Quantos estão em SICK?

Quantos estão emprestados?

Quantos estão em transferência?

Quais produtos possuem maior quantidade?

Quais bases possuem maior estoque?

Onde existem equipamentos indisponíveis?

---

## KPIs

Total de equipamentos.

Equipamentos ativos.

Equipamentos em SICK.

Transferências pendentes.

Empréstimos ativos.

Equipamentos em manutenção.

---

## Gráficos

Distribuição por categoria.

Distribuição por base.

Distribuição por status.

Ranking de produtos.

---

## Melhorias da Fase 2

Novo layout.

Cards executivos.

Filtros mais rápidos.

Drill-down.

Pesquisa mais intuitiva.

Visual inspirado em Power BI.

---

# Dashboard Operacional

## Público

Operadores e Gestores.

---

## Objetivo

Acompanhar o dia a dia da operação.

---

## Deve responder

Quais inventários estão em andamento?

Quais checklists estão abertos?

Quais equipamentos ainda não retornaram?

Quais bases possuem estoque crítico?

Quais movimentações ocorreram hoje?

Quais equipamentos entraram em SICK?

---

## KPIs

Inventários em andamento.

Checklists em aberto.

Entradas de estoque.

Saídas de estoque.

Perdas.

Pendências.

---

# Dashboard Compras

## Público

Equipe de Compras.

---

## Objetivo

Permitir planejamento eficiente de aquisição de insumos.

---

## Deve responder

Quais itens precisam ser comprados?

Quais estão abaixo do estoque mínimo?

Qual categoria mais consome?

Quais preços foram alterados?

Qual consumo médio mensal?

Quanto será necessário comprar no próximo período?

---

## KPIs

Itens abaixo do mínimo.

Valor estimado de compra.

Consumo médio.

Itens mais consumidos.

Categorias mais consumidas.

Preço médio dos insumos.

---

## Gráficos

Top insumos.

Consumo mensal.

Consumo por categoria.

Estoque crítico.

Projeção de compras.

---

## Melhorias Futuras

Curva ABC.

Lead time.

Comparação entre fornecedores.

Sugestão automática de compra.

---

# Dashboard Planejamento

## Público

Planejamento.

---

## Objetivo

Preparar recursos para operações futuras.

---

## Deve responder

Quais inventários estão planejados?

Quais recursos serão necessários?

Quais bases precisarão de reposição?

Qual consumo previsto?

Existe risco de falta de insumos?

---

## KPIs

Inventários planejados.

Consumo previsto.

Bases críticas.

Necessidade de compra.

Capacidade operacional.

---

## Integração

Este dashboard deverá futuramente consumir informações do sistema de Planejamento via API.

---

# Dashboard Financeiro

## Público

Financeiro.

---

## Objetivo

Analisar custos operacionais.

---

## Deve responder

Quanto foi consumido?

Quanto foi perdido?

Qual categoria possui maior custo?

Qual cliente gera maior custo?

Qual base possui maior custo?

Qual grupo possui maior custo?

---

## KPIs

Custo total.

Perdas.

Custo médio.

Categorias.

Clientes.

Grupos.

---

## Gráficos

Custo mensal.

Categorias.

Clientes.

Grupos.

Top inventários.

---

# Dashboard Executivo

## Público

Diretoria.

---

## Objetivo

Apresentar visão consolidada da operação.

---

## Deve responder

Quanto custa cada cliente?

Quanto custa cada base?

Quanto custa cada grupo?

Qual o custo médio por inventário?

Quais categorias mais consomem recursos?

Quanto foi perdido?

Quanto foi reutilizado?

Qual a projeção de compras?

Como os custos evoluíram ao longo do tempo?

---

## KPIs

Custo total.

Custo por cliente.

Custo por base.

Custo por grupo.

Custo médio por inventário.

Consumo por categoria.

Perdas.

Reutilização.

Economia obtida com reutilização.

---

## Gráficos

Linha temporal de custos.

Ranking de clientes.

Ranking de grupos.

Ranking de bases.

Categorias.

Perdas.

Reutilização.

---

## Indicadores Estratégicos

Custo médio por inventário.

Custo médio por cliente.

Custo médio por grupo.

Percentual de reutilização.

Percentual de perdas.

Valor economizado.

Projeção de compras.

---

# Dashboard SICK

## Público

Gestores.

---

## Objetivo

Controlar equipamentos indisponíveis.

---

## Deve responder

Quantos equipamentos estão em SICK?

Qual categoria apresenta maior incidência?

Qual modelo possui maior recorrência?

Quanto tempo os equipamentos permanecem em SICK?

Quais bases possuem maior índice de problemas?

---

## KPIs

Equipamentos em SICK.

Tempo médio.

Reincidência.

Problemas por categoria.

Problemas por base.

---

# Dashboard TAGs

## Público

Operação e Compras.

---

## Objetivo

Controlar utilização de TAGs.

---

## Deve responder

Quantas TAGs foram utilizadas?

Quanto foi gasto?

Qual lote está acabando?

Qual base consome mais?

Existe desperdício?

---

## KPIs

TAGs utilizadas.

Valor consumido.

Valor por inventário.

Saldo por lote.

Lotes críticos.

---

## Gráficos

Consumo por mês.

Consumo por base.

Consumo por cliente.

Consumo por grupo.

---

# Dashboard Usuários

## Público

Administradores.

---

## Objetivo

Acompanhar utilização do sistema.

---

## Deve responder

Usuários ativos.

Último acesso.

Perfis existentes.

Distribuição por base.

Distribuição por idioma.

---

# Dashboard Notificações

## Público

Todos.

---

## Objetivo

Centralizar eventos importantes.

---

## Deve responder

Quais notificações existem?

Quais ainda não foram lidas?

Quais são críticas?

Quais dependem de ação?

---

# Indicadores Compartilhados

Os indicadores abaixo podem aparecer em mais de um dashboard.

* custo por cliente;
* custo por base;
* custo por grupo;
* custo por inventário;
* consumo por categoria;
* estoque crítico;
* perdas;
* reutilização;
* inventários;
* SICK;
* transferências;
* empréstimos.

---

# Drill-down

Sempre que possível:

```text
Grupo

↓

Base

↓

Inventário

↓

Checklist

↓

Insumos

↓

Movimentações
```

Outro exemplo:

```text
Cliente

↓

Inventários

↓

Checklist

↓

Custo

↓

Itens Consumidos
```

---

# Atualização dos Dados

Todos os dashboards devem consumir dados produzidos pelos Services.

Nenhum dashboard deve recalcular regras de negócio.

---

# Visual da Fase 2

Os dashboards passarão por redesign inspirado em ferramentas de Business Intelligence.

Características desejadas:

* cartões executivos;
* filtros rápidos;
* gráficos modernos;
* navegação intuitiva;
* drill-down;
* consistência visual;
* alto contraste;
* foco na informação.

O objetivo é aproximar a experiência de uso de soluções como Power BI, mantendo simplicidade para o usuário operacional.

---

# Evolução Futura

A camada de BI deverá evoluir continuamente.

Funcionalidades previstas:

* metas;
* comparativos anuais;
* indicadores por período;
* tendências;
* previsões;
* alertas inteligentes;
* exportação para Excel e PDF;
* compartilhamento de painéis;
* favoritos;
* dashboards personalizados por perfil.

---

# Conclusão

Os dashboards representam a tradução dos dados operacionais em inteligência de negócio.

Seu objetivo principal é responder perguntas, apoiar decisões e permitir que Operação, Compras, Planejamento, Financeiro e Diretoria acompanhem a evolução da empresa por meio de informações confiáveis, atualizadas e fáceis de interpretar.
