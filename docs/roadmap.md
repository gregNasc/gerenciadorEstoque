# 13 — Roadmap

## Objetivo

Este documento apresenta a estratégia de evolução do Gerenciador de Estoque.

O roadmap não representa apenas uma lista de funcionalidades, mas uma sequência lógica de evolução da plataforma.

Cada fase deve ser concluída antes do início da seguinte, preservando estabilidade, qualidade e documentação.

---

# Visão de Longo Prazo

O objetivo do projeto é evoluir de um sistema operacional de controle de estoque para uma plataforma integrada de gestão operacional, financeira e analítica.

```text
Controle Operacional

↓

Gestão

↓

Business Intelligence

↓

Integrações

↓

Plataforma Corporativa
```

---

# Fase 1 — Fundação (Concluída)

## Objetivos

* Controle de equipamentos.
* Cadastro de produtos.
* Transferências.
* Empréstimos.
* Histórico.
* SICK.
* Autenticação.
* Controle por bases.
* Deploy inicial.

---

# Fase 2 — Consolidação (Em andamento)

## Objetivos

* Documentação técnica.
* Refatoração módulo por módulo.
* Padronização dos Services.
* Padronização das APIs.
* Refatoração dos templates.
* Dashboards profissionais.
* Internacionalização.
* Infraestrutura preparada para crescimento.

---

## Ordem de Refatoração

### 1. Estoque

* Dashboard principal.
* Cadastro de equipamentos.
* Cadastro de usuários.
* Transferências.
* Empréstimos.
* Histórico.
* SICK.

---

### 2. Insumos

* Cadastro.
* Solicitações.
* Movimentações.
* Inventários.
* Checklists.
* TAGs.
* Consumo.
* Dashboards.

---

### 3. Comunicação

* Comunicados.
* Notificações.
* WhatsApp.
* E-mail.

---

### 4. Business Intelligence

* Dashboard Executivo.
* Dashboard Financeiro.
* Dashboard Compras.
* Dashboard Planejamento.
* Dashboard Operacional.
* Dashboard de Performance.

---

# Fase 3 — Integração

## Objetivos

* Integração com Planejamento.
* APIs padronizadas.
* Exportações.
* Importações.
* Integração com Power BI.
* Integração com WhatsApp.

---

# Fase 4 — Infraestrutura

## Objetivos

* Amazon S3.
* Pipeline CI/CD.
* Backups automatizados.
* Monitoramento.
* Logs centralizados.
* Ambiente de homologação.
* Migração gradual para AWS.

---

# Fase 5 — Inteligência

## Objetivos

* Projeção de compras.
* Tendências de consumo.
* Comparativos históricos.
* Alertas inteligentes.
* Indicadores preditivos.
* Regras automáticas de reposição.

---

# Evoluções Planejadas

## Operação

* Melhorias contínuas nos checklists.
* Melhorias no SICK.
* Melhorias em empréstimos.
* Melhorias em transferências.

---

## Compras

* Curva ABC.
* Histórico de preços.
* Fornecedores.
* Lead Time.
* Sugestão automática de compra.

---

## Planejamento

* Consumo previsto.
* Necessidade futura.
* Integração completa.
* Simulações.

---

## Financeiro

* Comparativos.
* Tendências.
* Indicadores.
* Custo previsto versus realizado.

---

## Executivo

* Indicadores estratégicos.
* Dashboards consolidados.
* Performance operacional.
* Economia obtida com reutilização.

---

# Internacionalização

Idiomas previstos:

* Português.
* Espanhol.

Idiomas futuros poderão ser adicionados mantendo toda a interface traduzível.

---

# Aplicação Móvel (Longo Prazo)

Possibilidades:

* Consulta de equipamentos.
* Consulta de inventários.
* Checklist.
* Leitura por QR Code.
* Notificações Push.

---

# Critérios para cada nova funcionalidade

Toda nova funcionalidade deverá seguir obrigatoriamente:

```text
Discussão

↓

Documentação

↓

Modelagem

↓

Implementação

↓

Testes

↓

Deploy
```

---

# Objetivo Final

O Gerenciador de Estoque deverá tornar-se uma plataforma única para gestão operacional, controle patrimonial, controle de insumos, planejamento, custos e inteligência de negócio.

O crescimento deverá acontecer de forma incremental, preservando simplicidade, estabilidade e facilidade de manutenção.
