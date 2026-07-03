# 02 — Arquitetura do Projeto

## Visão Geral

O Gerenciador de Estoque é estruturado como uma aplicação web Django, organizada em módulos com responsabilidades bem definidas.

A arquitetura deve favorecer:

* separação de responsabilidades;
* regras de negócio centralizadas;
* evolução incremental;
* integração entre módulos;
* facilidade de manutenção;
* geração de indicadores;
* futura expansão para APIs, BI e integrações externas.

---

## Estrutura Principal

```text
gerenciadorEstoque/
│
├── core/
├── estoque/
├── insumos/
├── templates/
├── static/
├── media/
├── docs/
├── manage.py
└── requirements.txt
```

---

## Apps Principais

### core

Responsável por funcionalidades globais do sistema.

Pode conter:

* configurações auxiliares;
* middlewares;
* utilitários compartilhados;
* regras comuns;
* filtros globais;
* base para internacionalização;
* componentes reutilizáveis.

---

### estoque

Responsável pelo controle de equipamentos e movimentações físicas.

Principais responsabilidades:

* cadastro de equipamentos;
* controle por base;
* status dos equipamentos;
* transferências;
* empréstimos;
* SICK;
* histórico;
* dashboard principal;
* comunicados;
* usuários e permissões relacionadas ao estoque.

---

### insumos

Responsável pelo controle de materiais, inventários, checklists, consumo e custos.

Principais responsabilidades:

* cadastro de insumos;
* movimentações de insumos;
* solicitações;
* inventários;
* checklists;
* controle de TAGs;
* consumo por inventário;
* custos;
* dashboards operacionais, financeiros, compras, planejamento e executivo.

---

## Camadas da Aplicação

O projeto deve seguir uma divisão lógica em camadas.

```text
Template
   ↓
View
   ↓
Form / Serializer
   ↓
Service
   ↓
Model
   ↓
Database
```

---

## Templates

Os templates são responsáveis apenas pela apresentação.

Devem conter:

* HTML;
* Bootstrap/CSS;
* componentes visuais;
* exibição de dados;
* formulários;
* pequenas validações de interface.

Os templates não devem conter regras críticas de negócio.

---

## Views

As views devem controlar o fluxo da requisição.

Responsabilidades principais:

* receber requisições;
* validar permissões;
* carregar dados;
* chamar services;
* retornar templates ou JSON;
* tratar mensagens de sucesso ou erro.

As views não devem concentrar regras complexas de negócio.

---

## Forms

Os forms devem validar dados de entrada.

Responsabilidades:

* validação de campos;
* filtros de queryset;
* regras simples de formulário;
* adaptação da entrada do usuário.

Regras operacionais complexas devem ser delegadas aos services.

---

## Services

Os services são a camada principal de regra de negócio.

Devem concentrar fluxos como:

* movimentar estoque;
* gerar histórico;
* finalizar checklist;
* calcular consumo;
* calcular custo;
* registrar perdas;
* registrar devoluções;
* validar saldo;
* gerar notificações;
* aplicar regras financeiras.

Essa camada deve ser priorizada nas refatorações.

---

## Models

Os models representam as entidades do domínio.

Devem conter:

* campos;
* relacionamentos;
* constraints;
* índices;
* permissões;
* propriedades simples.

Sempre que possível, lógica pesada deve ficar fora dos models e dentro dos services.

---

## Banco de Dados

O banco de dados é responsável pela persistência das informações.

Principais grupos de dados:

* usuários;
* perfis;
* empresas;
* bases;
* grupos de bases;
* equipamentos;
* produtos;
* históricos;
* solicitações;
* transferências;
* empréstimos;
* insumos;
* inventários;
* checklists;
* movimentações;
* consumos;
* custos;
* notificações.

---

## Integração entre Estoque e Insumos

Os apps `estoque` e `insumos` são separados, mas integrados.

A integração acontece principalmente por:

* Base;
* usuário;
* equipamento;
* inventário;
* checklist;
* histórico;
* dashboards.

Exemplo:

```text
Base
 ↓
Equipamentos disponíveis no estoque
 ↓
Checklist do inventário
 ↓
Equipamentos enviados
 ↓
Equipamentos retornados
```

Outro exemplo:

```text
Inventário
 ↓
Checklist
 ↓
Insumos enviados
 ↓
Insumos consumidos / retornados / perdidos
 ↓
ConsumoInsumo
 ↓
Dashboard financeiro
```

---

## Fluxo Operacional de Inventário

```text
Inventário criado
        ↓
Checklist aberto
        ↓
Equipamentos selecionados
        ↓
Insumos selecionados
        ↓
TAGs informadas por faixa
        ↓
Inventário executado
        ↓
Retorno registrado
        ↓
Checklist finalizado
        ↓
Movimentações geradas
        ↓
Consumo calculado
        ↓
Custo apurado
        ↓
Dashboards atualizados
```

---

## Fluxo de Custo

O custo deve ser calculado com base no consumo efetivo.

```text
Insumo enviado
        ↓
Quantidade utilizada / perdida / retornada
        ↓
Quantidade consumida apurada
        ↓
Valor unitário aplicado
        ↓
Custo total gerado
        ↓
Vinculação ao inventário
```

Para TAGs:

```text
Valor do rolo
        ↓
Quantidade de TAGs do rolo
        ↓
Valor unitário da TAG
        ↓
Faixa utilizada
        ↓
Quantidade utilizada
        ↓
Custo da faixa
```

---

## Dashboards

Os dashboards devem consumir dados consolidados pelos services ou queries específicas.

Tipos previstos:

### Dashboard Principal

Visão geral do estoque de equipamentos.

### Dashboard Operacional

Visão da operação por base.

### Dashboard Compras

Indicadores de consumo, preço, estoque mínimo e necessidade de reposição.

### Dashboard Planejamento

Inventários, previsão de demanda e consumo previsto.

### Dashboard Financeiro

Custos, consumo, perdas e indicadores financeiros.

### Dashboard Executivo

KPIs consolidados para diretoria.

---

## APIs Internas

As APIs internas devem ser utilizadas para:

* alimentar gráficos;
* atualizar selects dinâmicos;
* buscar equipamentos por base;
* buscar insumos por categoria;
* carregar dados de dashboards;
* retornar indicadores.

Exemplos:

```text
/insumos/api/kpis/inventarios/
/insumos/api/bi/consumo-base/
/insumos/api/bi/ranking-insumos/
/insumos/api/bi/consumo-mes/
```

---

## Integrações Futuras

A arquitetura deve estar preparada para integrações externas.

Integrações previstas:

* sistema de Planejamento via API;
* notificações por WhatsApp;
* notificações por e-mail;
* possíveis integrações com dashboards externos;
* futura migração de infraestrutura;
* internacionalização para espanhol.

---

## Sistema de Notificações

A arquitetura de notificações deve ser plugável.

Canais possíveis:

* dashboard interno;
* e-mail;
* WhatsApp;
* push futuramente.

A regra principal é:

```text
A ação operacional acontece uma vez
        ↓
O sistema gera um evento/comunicado
        ↓
Os canais configurados replicam a mensagem
```

A regra de negócio da ação não deve depender diretamente do canal de envio.

---

## Internacionalização

O sistema deve estar preparado para português e espanhol.

Boas práticas:

* usar `{% trans %}` nos templates;
* usar `gettext_lazy` nos models e forms;
* evitar textos fixos espalhados;
* centralizar labels importantes;
* revisar cadastros e mensagens para tradução.

---

## Infraestrutura

Ambiente atual:

* aplicação Django;
* deploy no Render;
* banco PostgreSQL;
* arquivos estáticos com WhiteNoise;
* Gunicorn em produção.

Evolução futura:

* estudar migração do Render para nova infraestrutura;
* avaliar armazenamento de arquivos;
* revisar deploy;
* revisar variáveis de ambiente;
* preparar monitoramento;
* preparar backup;
* melhorar observabilidade.

---

## Princípios Arquiteturais

### 1. Separação por domínio

Cada app deve cuidar do seu domínio principal.

`estoque` não deve absorver regras de insumos.
`insumos` não deve duplicar regras de equipamentos.

---

### 2. Services como centro da regra

Fluxos críticos devem estar em services.

Exemplos:

* `ChecklistService`;
* `MovimentacaoService`;
* `ConsumoService`;
* `DashboardService`;
* futuros services de notificações e compras.

---

### 3. Templates simples

Templates devem apresentar dados e capturar ações.

Não devem decidir regra de negócio complexa.

---

### 4. Evolução incremental

A arquitetura deve ser melhorada sem reescrever tudo.

A regra é:

```text
Refatorar
↓
Testar
↓
Validar
↓
Seguir
```

---

### 5. Dados confiáveis

Toda movimentação relevante deve gerar histórico ou registro rastreável.

O sistema deve permitir auditoria das principais ações.

---

### 6. BI como consequência dos dados

Dashboards não devem ser alimentados manualmente.

Eles devem nascer dos dados operacionais registrados corretamente.

---

## Direção Técnica da Fase 2

Durante a Fase 2, a arquitetura deve evoluir para:

* services mais organizados;
* views menores;
* templates mais limpos;
* dashboards mais consistentes;
* permissões mais claras;
* APIs internas mais padronizadas;
* documentação oficial;
* suporte futuro a testes automatizados;
* suporte a internacionalização;
* preparação para integração externa.

---

## Resumo

A arquitetura do Gerenciador de Estoque deve sustentar um sistema operacional, financeiro e gerencial.

Ela precisa permitir que o projeto continue crescendo sem perder organização.

O foco não é apenas fazer novas funcionalidades, mas garantir que cada nova funcionalidade siga uma estrutura clara, documentada e sustentável.
