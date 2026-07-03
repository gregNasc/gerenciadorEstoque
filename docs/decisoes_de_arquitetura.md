# 14 — Decisões de Arquitetura (ADR)

## Objetivo

Este documento registra as principais decisões arquiteturais tomadas durante o desenvolvimento do Gerenciador de Estoque.

Seu objetivo é preservar o contexto técnico e operacional por trás de cada decisão importante.

Sempre que uma decisão estrutural for tomada, um novo registro deverá ser acrescentado.

---

# ADR-001 — Separação entre Estoque e Insumos

## Decisão

Criar dois módulos independentes.

## Motivo

Equipamentos possuem ciclo de vida completamente diferente dos insumos.

Misturar ambos aumentaria a complexidade e dificultaria a evolução.

## Consequência

Cada módulo evolui de forma independente, compartilhando apenas os pontos realmente necessários.

---

# ADR-002 — Regras centralizadas em Services

## Decisão

Toda regra de negócio importante deve estar em Services.

## Motivo

Evitar duplicação entre Views, APIs, comandos e integrações.

## Consequência

A lógica da empresa permanece em um único lugar.

---

# ADR-003 — Custo calculado pelo consumo

## Decisão

O custo será calculado apenas pelo consumo efetivo.

## Motivo

Itens enviados podem retornar ao estoque.

Enviar não significa consumir.

## Consequência

Os indicadores financeiros representam a realidade operacional.

---

# ADR-004 — Insumos reutilizáveis

## Decisão

Criar o conceito de insumo reutilizável.

## Motivo

Diversos materiais retornam após o inventário e continuam sendo utilizados.

Exemplos:

* durex;
* balança;
* escada;
* botas;
* transformadores.

## Consequência

O sistema mede consumo real e economia obtida com reutilização.

---

# ADR-005 — Controle de TAGs por faixa

## Decisão

As TAGs serão controladas por intervalos numéricos.

## Motivo

A operação utiliza faixas contínuas de etiquetas.

## Consequência

É possível calcular quantidade utilizada e custo com precisão.

---

# ADR-006 — Dashboards por perfil

## Decisão

Cada perfil possui um dashboard próprio.

## Motivo

Cada área responde perguntas diferentes.

Operação não precisa da mesma visão do Financeiro.

## Consequência

Interfaces mais objetivas e úteis.

---

# ADR-007 — Documentação como parte do produto

## Decisão

A documentação possui o mesmo valor do código.

## Motivo

Facilitar manutenção, onboarding e evolução.

## Consequência

Toda funcionalidade relevante nasce documentada.

---

# ADR-008 — Arquitetura guiada pela operação

## Decisão

A operação define o software.

## Motivo

O sistema existe para apoiar o trabalho das equipes.

## Consequência

As regras de negócio sempre prevalecem sobre conveniências técnicas.

---

# ADR-009 — Business Intelligence integrado

## Decisão

O BI faz parte da plataforma.

## Motivo

Indicadores devem nascer dos dados operacionais, e não de planilhas paralelas.

## Consequência

Compras, Planejamento, Financeiro e Diretoria trabalham sobre a mesma base de dados.

---

# ADR-010 — Preparação para integrações

## Decisão

Toda integração ocorrerá por APIs e Services.

## Motivo

Reduzir acoplamento e facilitar evolução.

## Consequência

Novos sistemas poderão ser integrados sem alterar as regras centrais.

---

# ADR-011 — Evolução gradual da infraestrutura

## Decisão

Utilizar Render na fase inicial e migrar gradualmente para AWS.

## Motivo

Equilibrar simplicidade, custo e escalabilidade.

## Consequência

A infraestrutura acompanha o crescimento do produto.

---

# ADR-012 — Refatoração incremental

## Decisão

Refatorar módulo por módulo.

## Motivo

Reduzir risco e manter o sistema sempre utilizável.

## Consequência

Cada evolução é pequena, validada e segura.

---

# Como registrar novas ADRs

Cada nova decisão deve conter:

* Contexto.
* Problema.
* Alternativas consideradas.
* Decisão tomada.
* Motivo.
* Consequências.
* Data.
* Versão do sistema.

---

# Filosofia Final

Toda decisão arquitetural deve responder a três perguntas:

1. Resolve um problema real da operação?
2. Simplifica a evolução do sistema?
3. Continua fazendo sentido daqui a alguns anos?

Se qualquer resposta for negativa, a decisão deve ser reavaliada.

---

# Conclusão

As ADRs preservam a memória técnica do projeto.

Elas garantem que futuras evoluções respeitem os princípios definidos durante a construção do Gerenciador de Estoque, permitindo crescimento consistente, previsível e alinhado à operação.
