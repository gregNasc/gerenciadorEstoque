# 06 — Services

## Objetivo

Os Services representam a camada de regras de negócio do Gerenciador de Estoque.

Toda operação importante do sistema deve acontecer através de um Service.

A responsabilidade dos Services é garantir que as regras da operação sejam executadas de forma consistente, reutilizável, auditável e independente da interface utilizada (Web, API ou futuras integrações).

---

# Filosofia

Um Service responde à pergunta:

> **"Como esta operação funciona?"**

Ele não responde:

> "Como esta tela funciona?"

Nem:

> "Como este botão funciona?"

Os Services representam o comportamento da empresa.

---

# Fluxo Geral

```text
Usuário

↓

View

↓

Formulário / API

↓

Service

↓

Models

↓

Histórico

↓

Dashboards

↓

Notificações
```

---

# Princípios

## Um Service representa uma operação.

Exemplos:

* finalizar checklist;
* registrar consumo;
* movimentar estoque;
* aprovar solicitação;
* receber transferência.

---

## Um Service deve ser reutilizável.

Uma mesma regra deve funcionar para:

* tela web;
* API;
* comando;
* integração futura.

---

## Um Service nunca depende do template.

O template apenas solicita a operação.

---

## Um Service pode utilizar outros Services.

Exemplo:

```text
ChecklistService

↓

MovimentacaoService

↓

ConsumoService

↓

DashboardService
```

---

## Um Service deve gerar consequências completas.

Exemplo:

Finalizar um checklist não significa apenas mudar um status.

Também significa:

* movimentar estoque;
* registrar consumo;
* registrar perdas;
* atualizar histórico;
* atualizar indicadores.

---

# ChecklistService

## Objetivo

Controlar todo o ciclo de vida operacional de um checklist.

É um dos Services mais importantes do sistema.

---

## Responsabilidades

* criar checklist;
* adicionar equipamentos;
* adicionar insumos;
* adicionar TAGs;
* registrar retornos;
* validar regras;
* finalizar checklist;
* gerar movimentações;
* gerar consumo;
* atualizar histórico.

---

## Fluxo

```text
Criar Checklist

↓

Selecionar Equipamentos

↓

Selecionar Insumos

↓

Selecionar TAGs

↓

Executar Inventário

↓

Registrar Retornos

↓

Registrar Perdas

↓

Validar

↓

Finalizar

↓

Movimentações

↓

Consumo

↓

Dashboards
```

---

## Models Utilizados

* ChecklistDiario
* ItemChecklist
* ChecklistEquipamento
* ChecklistLoteTag
* MovimentacaoTag
* Inventario

---

## Services Utilizados

* MovimentacaoService
* ConsumoService
* DashboardService

---

## Regras Importantes

Não permitir finalizar checklist sem retorno de equipamentos.

Não permitir inconsistência de quantidades.

Não permitir consumo negativo.

Gerar histórico automaticamente.

Gerar consumo automaticamente.

---

## Consequências

Atualiza estoque.

Atualiza custos.

Atualiza dashboards.

Atualiza histórico.

---

## Evoluções Futuras

Checklist parcialmente finalizado.

Assinatura digital.

Anexos.

Fotos.

Workflow de aprovação.

---

# MovimentacaoService

## Objetivo

Controlar toda movimentação de insumos.

É o único responsável por alterar saldo de estoque.

---

## Responsabilidades

* entrada;
* saída;
* devolução;
* perda;
* ajuste.

---

## Fluxo

```text
Recebe operação

↓

Valida saldo

↓

Atualiza estoque

↓

Atualiza custo médio

↓

Gera histórico

↓

Atualiza dashboards
```

---

## Models Utilizados

* MovimentacaoInsumo
* Insumo

---

## Regras

Saldo nunca pode ficar negativo.

Perdas geram custo.

Devoluções aumentam saldo.

Ajustes exigem justificativa.

---

## Consequências

Atualiza estoque.

Atualiza histórico.

Atualiza indicadores.

---

## Evoluções Futuras

Lotes de compra.

Fornecedor.

Integração financeira.

---

# ConsumoService

## Objetivo

Transformar utilização operacional em custo financeiro.

---

## Responsabilidades

Calcular consumo.

Calcular valor.

Gerar ConsumoInsumo.

Atualizar indicadores.

---

## Fluxo

```text
ItemChecklist

↓

Quantidade Consumida

↓

Valor Médio

↓

Valor Total

↓

ConsumoInsumo

↓

Dashboard
```

---

## Regras

Itens retornados não geram consumo.

Itens reutilizados não geram consumo enquanto retornarem ao estoque.

Perdas geram custo.

TAGs calculam custo pela faixa utilizada.

---

## Dashboards Impactados

Compras.

Financeiro.

Executivo.

---

## Evoluções Futuras

Comparação entre custo previsto e realizado.

---

# DashboardService

## Objetivo

Centralizar toda lógica necessária para alimentar dashboards.

---

## Responsabilidades

Consolidar informações.

Agrupar dados.

Gerar KPIs.

Preparar gráficos.

---

## Princípio

Dashboards nunca devem recalcular regras operacionais.

Eles devem consumir dados já consolidados.

---

## Dashboards Atendidos

Operacional.

Compras.

Planejamento.

Financeiro.

Executivo.

---

## Indicadores

Custo por cliente.

Custo por base.

Custo por grupo.

Consumo.

Perdas.

Reutilização.

Inventários.

Equipamentos.

SICK.

---

## Evoluções Futuras

Cache.

Indicadores históricos.

Comparativos anuais.

Metas.

---

# ComunicadoService

## Objetivo

Registrar acontecimentos relevantes do sistema.

---

## Responsabilidades

Criar comunicados.

Padronizar mensagens.

Registrar eventos.

---

## Princípio

O comunicado representa o evento.

O canal de envio é outra responsabilidade.

---

## Eventos

Transferência.

Empréstimo.

Recebimento.

Devolução.

Solicitação.

Inventário.

Checklist.

Compras.

---

## Evoluções Futuras

Templates de mensagem.

Notificações inteligentes.

Agrupamento de eventos.

---

# NotificacaoService (Planejado)

## Objetivo

Distribuir comunicados para diferentes canais.

---

## Canais

Dashboard.

WhatsApp.

E-mail.

Push.

---

## Fluxo

```text
Evento

↓

Comunicado

↓

Notificação

↓

Canal
```

---

# CompraService (Planejado)

## Objetivo

Centralizar regras de compras.

---

## Responsabilidades

Cadastrar insumos.

Atualizar preços.

Controlar estoque mínimo.

Gerar necessidade de compra.

Projetar consumo.

---

## Dashboards

Compras.

Executivo.

Planejamento.

---

# PlanejamentoService (Planejado)

## Objetivo

Preparar informações operacionais futuras.

---

## Responsabilidades

Importar dados externos.

Calcular necessidade de recursos.

Projetar consumo.

Integrar APIs.

---

# Dependências

```text
ChecklistService

↓

MovimentacaoService

↓

ConsumoService

↓

DashboardService

↓

ComunicadoService

↓

NotificacaoService
```

---

# Regras Gerais

Todos os Services devem:

* possuir responsabilidade única;
* ser reutilizáveis;
* ser independentes da interface;
* centralizar regras de negócio;
* registrar histórico quando necessário;
* atualizar dashboards quando necessário;
* ser preparados para testes automatizados.

---

# Boas Práticas

Views pequenas.

Services grandes.

Models simples.

Templates limpos.

Regras centralizadas.

Documentação atualizada.

---

# Objetivo da Fase 2

Ao final da Fase 2, todos os fluxos críticos do sistema deverão estar representados por Services claramente documentados, reutilizáveis e testáveis.

Essa camada será considerada o núcleo da inteligência do Gerenciador de Estoque.
