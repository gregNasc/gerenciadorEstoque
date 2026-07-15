# API de Integração — Inventory Planning

API read-only. Fornece dados de eventos de inventário planejados, colaboradores, equipes, disponibilidade e dados de referência necessários para montar escalas de trabalho.

**Base URL (produção):** `https://dab41miq8jzsq.cloudfront.net/api/integration/v1`

**Versão:** 1.0

> Todas as requisições devem usar **HTTPS**. Requisições HTTP são redirecionadas automaticamente (301).

---

## Sumário

1. [Visão Geral](#visão-geral)
2. [Guia Rápido de Integração](#guia-rápido-de-integração)
3. [Autenticação](#autenticação)
4. [Rate Limiting](#rate-limiting)
5. [Formato de Resposta](#formato-de-resposta)
6. [Paginação](#paginação)
7. [Mapa de Rotas](#mapa-de-rotas)
8. [Glossário](#glossário)
9. [Enumerações e Valores Permitidos](#enumerações-e-valores-permitidos)
10. [Rotas — Planejamento](#rotas--planejamento)
11. [Rotas — Colaboradores](#rotas--colaboradores)
12. [Rotas — Catálogos](#rotas--catálogos)
13. [Rotas — Infraestrutura](#rotas--infraestrutura)
14. [Cenários de Uso](#cenários-de-uso)
15. [Códigos de Erro](#códigos-de-erro)

---

## Visão Geral

Esta API expõe dados do sistema de planejamento de inventários para que o sistema de escalas possa:

- **Consultar eventos planejados** — saber onde, quando e que tipo de inventário será realizado, quantas peças são esperadas, endereço, pessoas previstas, horário de início e qual equipe já está atribuída.
- **Consultar colaboradores elegíveis** — obter dados pessoais, profissão, classificação, vínculo, disponibilidade, localização, dados bancários e composição de valor estimado apenas de colaboradores cujo status no DP esteja apto para escalas (`status.isActiveState = true`).
- **Consultar equipes por hierarquia** — navegar a árvore de subordinados de um gerente, coordenador ou gestor.
- **Buscar conferentes avulsos** — encontrar colaboradores esporádicos disponíveis por regional, empresa e dias da semana.
- **Consultar dados de referência** — profissões, classificações, tipos de vínculo, status e empresas.

### Hierarquia de equipe

A equipe de campo segue esta estrutura hierárquica:

```
GERENTE
  └── COORDENADOR
        └── LIDER
              └── CONFERENTE
```

Cada nível supervisiona o nível abaixo. A rota `/collaborators/:id/team` retorna essa árvore recursivamente.

### Elegibilidade para escalas

As rotas de colaboradores desta API servem apenas pessoas que:

- não estejam removidas (`deletedAt = null`)
- possuam um status do DP com `isActiveState = true`

Na prática:

- **status apto para escala** → colaborador elegível para a integração
- **status restritivo / bloqueado** → colaborador não aparece nas rotas relevantes da integração
- **colaborador sem status** → também não é servido pela integração

### Hierarquia de eventos (PAI / FILHO)

Todo inventário planejado é um **evento**. Eventos seguem a hierarquia PAI/FILHO:

- **Evento PAI** — o inventário principal (ex: "Inventário Oficial"). Possui `parentEventId = null`.
- **Evento FILHO** — atividade vinculada ao PAI, realizada antes ou depois (ex: "Folga", "Arrumação", "Contagem Antecipada"). Possui `parentEventId` preenchido apontando para o PAI.

Quando você consulta um evento PAI, o campo `children` traz todos os eventos FILHO vinculados. Quando consulta um evento FILHO, o campo `parentEvent` traz o resumo do PAI.

---

## Guia Rápido de Integração

Fluxo típico para montar uma escala:

### Passo 1 — Buscar eventos do mês

```
GET /events?month=2026-03&parentOnly=true&status=PLANNED,CANCELLED,MODIFIED
```

Retorna todos os eventos PAI planejados/aprovados de março, cada um com seus eventos FILHO aninhados em `children`.

### Passo 2 — Ver detalhes de um evento

```
GET /events/{eventId}
```

Retorna o evento completo: data, loja, regional, tipo de inventário, número de peças planejadas, endereço, pessoas previstas, horário de início (`importData`), métricas (`metrics`), equipe atribuída e ordens de serviço.

### Passo 3 — Buscar a equipe de um gerente

```
GET /collaborators/{gerenteId}/team
```

Retorna toda a árvore de subordinados do gerente (coordenadores, gestores e conferentes) com dados de contato e disponibilidade.

### Passo 4 — Buscar conferentes avulsos disponíveis

```
GET /collaborators/sporadic?regionalId={id}&availableWeekdays=MONDAY
```

Retorna conferentes avulsos da regional que estão disponíveis nas segundas-feiras.

### Passo 5 — Consultar dados de referência

```
GET /catalogs/professions
GET /catalogs/classifications
GET /catalogs/employment-types
```

Retorna os dados de referência para mapear IDs de profissão, classificação e vínculo.

---

## Autenticação

Todas as rotas exigem uma **API Key** no header `X-API-Key`.

```
X-API-Key: ipk_sua_chave_aqui
```

A API Key fornecida. Ela é prefixada com `ipk_` para fácil identificação.

### Erros de autenticação

| Status | Mensagem                                   | Quando acontece                         |
| ------ | ------------------------------------------ | --------------------------------------- |
| 401    | API Key ausente. Envie o header X-API-Key. | Header não enviado                      |
| 401    | API Key inválida.                          | Chave não reconhecida                   |
| 403    | API Key desativada.                        | Chave foi desativada pelo administrador |
| 403    | API Key expirada.                          | Chave ultrapassou a data de expiração   |

**Exemplo — sem API Key:**

```bash
curl https://dab41miq8jzsq.cloudfront.net/api/integration/v1/events
# → 401 {"error":{"message":"API Key ausente. Envie o header X-API-Key."}}
```

---

## Rate Limiting

A API possui limite de requisições para garantir estabilidade. O limite é aplicado **por API Key** (não por IP), ou seja, mesmo que você faça chamadas de múltiplos servidores usando a mesma chave, o limite é compartilhado.

| Limite                | Janela     | Identificador               |
| --------------------- | ---------- | --------------------------- |
| **1.000 requisições** | 15 minutos | Valor do header `X-Api-Key` |

### Headers de controle

Toda resposta inclui headers para monitorar o consumo:

| Header                | Descrição                             |
| --------------------- | ------------------------------------- |
| `RateLimit-Limit`     | Limite total da janela (1000)         |
| `RateLimit-Remaining` | Requisições restantes na janela atual |
| `RateLimit-Reset`     | Segundos até a janela reiniciar       |

### Quando o limite é atingido

Ao exceder o limite, a API retorna:

```
HTTP/1.1 429 Too Many Requests
Retry-After: 120
RateLimit-Limit: 1000
RateLimit-Remaining: 0
RateLimit-Reset: 120
```

```json
{
  "error": {
    "message": "Too many requests, please try again later."
  }
}
```

**Recomendações:**

- Respeite o header `Retry-After` antes de tentar novamente.
- Para sincronizações em lote, use `perPage=100` para reduzir o número de chamadas.
- Cachear dados de referência (catálogos, regionais, tipos de inventário) que mudam raramente.

---

## Formato de Resposta

### Item único

```json
{
  "data": { "id": "abc", "name": "..." }
}
```

### Lista paginada

```json
{
  "data": {
    "items": [ ... ],
    "meta": {
      "page": 1,
      "perPage": 20,
      "total": 150,
      "pageCount": 8
    }
  }
}
```

### Lista simples (catálogos pequenos)

```json
{
  "data": [ ... ]
}
```

### Erro

```json
{
  "error": {
    "message": "Descrição do erro"
  }
}
```

---

## Paginação

Todas as rotas de listagem paginada aceitam:

| Param     | Tipo | Default | Min | Max | Descrição        |
| --------- | ---- | ------- | --- | --- | ---------------- |
| `page`    | int  | 1       | 1   | -   | Página atual     |
| `perPage` | int  | 20      | 5   | 100 | Itens por página |

O campo `meta` na resposta contém `page`, `perPage`, `total` (total de registros) e `pageCount` (total de páginas).

---

## Mapa de Rotas

### Planejamento

| Método | Rota                   | Descrição                             |
| ------ | ---------------------- | ------------------------------------- |
| GET    | `/events`              | Listar eventos planejados com filtros |
| GET    | `/events/:id`          | Detalhe de um evento                  |
| GET    | `/events/:id/children` | Eventos FILHO de um evento PAI        |

### Colaboradores

| Método | Rota                       | Descrição                                                    |
| ------ | -------------------------- | ------------------------------------------------------------ |
| GET    | `/collaborators`           | Listar colaboradores com filtros                             |
| GET    | `/collaborators/sporadic`  | Listar conferentes avulsos                                   |
| GET    | `/collaborators/:id`       | Detalhe completo de um colaborador (com composição de valor) |
| GET    | `/collaborators/:id/value` | Composição de valor do colaborador                           |
| GET    | `/collaborators/:id/team`  | Árvore hierárquica de subordinados                           |

### Catálogos (dados de referência)

| Método | Rota                              | Descrição                                 |
| ------ | --------------------------------- | ----------------------------------------- |
| GET    | `/catalogs/professions`           | Profissões com hierarquia                 |
| GET    | `/catalogs/professions/:id`       | Detalhe de uma profissão                  |
| GET    | `/catalogs/work-functions`        | Funções operacionais                      |
| GET    | `/catalogs/work-functions/:id`    | Detalhe de uma função operacional         |
| GET    | `/catalogs/employment-types`      | Tipos de vínculo                          |
| GET    | `/catalogs/classifications`       | Classificações (com valor de bonificação) |
| GET    | `/catalogs/collaborator-statuses` | Status de colaborador com motivos         |
| GET    | `/catalogs/companies`             | Empresas com centros de custo             |
| GET    | `/catalogs/companies/:id`         | Detalhe de uma empresa                    |

### Infraestrutura

| Método | Rota                   | Descrição                        |
| ------ | ---------------------- | -------------------------------- |
| GET    | `/segments`            | Segmentos de mercado             |
| GET    | `/segments/:id`        | Detalhe de um segmento           |
| GET    | `/regions`             | Regionais com pontos de encontro |
| GET    | `/regions/:id`         | Detalhe de uma regional          |
| GET    | `/inventory-types`     | Tipos de inventário (PAI/FILHO)  |
| GET    | `/inventory-types/:id` | Detalhe de um tipo de inventário |
| GET    | `/clients`             | Clientes com segmento            |
| GET    | `/clients/:id`         | Detalhe de um cliente com lojas  |
| GET    | `/stores`              | Lojas com cliente e regional     |
| GET    | `/stores/:id`          | Detalhe de uma loja              |

---

## Glossário

| Termo                         | Descrição                                                                                                                                                         |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Evento**                    | Um inventário planejado em uma loja, com data, tipo e equipe.                                                                                                     |
| **Evento PAI**                | O inventário principal (ex: Inventário Oficial). Pode ter eventos FILHO vinculados.                                                                               |
| **Evento FILHO**              | Atividade vinculada a um PAI (ex: Folga, Arrumação, Contagem Antecipada).                                                                                         |
| **Regional**                  | Região operacional (ex: SP SUL, PR CURITIBA, RJ). Agrupa lojas e colaboradores.                                                                                   |
| **Loja (Store)**              | Estabelecimento do cliente onde o inventário é realizado.                                                                                                         |
| **Cliente (Client)**          | Empresa dona das lojas (ex: Lojas Riachuelo, Companhia Brasileira de Distribuição).                                                                               |
| **Segmento**                  | Setor de mercado do cliente (ex: Supermercado, Vestuário, Drogaria).                                                                                              |
| **Tipo de Inventário**        | Classificação do evento. Tipo PAI = inventário principal, tipo FILHO = atividade complementar.                                                                    |
| **Colaborador**               | Pessoa que trabalha nos inventários. Pode ser fixo ou avulso.                                                                                                     |
| **Conferente Avulso**         | Colaborador esporádico (`isSporadic = true`) que é chamado sob demanda, sem vínculo fixo com uma equipe.                                                          |
| **Profissão**                 | Função do colaborador na hierarquia: Conferente (1), Gestor (2), Coordenador (3), Gerente (4), Diretoria (5). Quanto maior o número, maior o nível hierárquico.   |
| **Classificação**             | Nível de qualificação do colaborador (ex: Classe A, Classe B), com valor de bonificação associado.                                                                |
| **Vínculo (Employment Type)** | Tipo de contrato: CLT, MEI, etc.                                                                                                                                  |
| **Disponibilidade**           | Turno em que o colaborador pode trabalhar: `DAY` (diurno), `NIGHT` (noturno) ou `ALL` (ambos).                                                                    |
| **Dias Disponíveis**          | Dias da semana em que o colaborador pode ser escalado (`availableWeekdays`).                                                                                      |
| **Supervisor**                | Colaborador que supervisiona outros. A relação é recursiva (gerente > coordenador > gestor > conferente).                                                         |
| **Composição de Valor**       | Estimativa de remuneração de um colaborador, calculada a partir da taxa por profissão na regional, bonificação por classificação e benefícios ativos da regional. |
| **Import Data**               | Dados brutos da planilha de importação de eventos. Contém informações como endereço, cidade, CEP, horário de início e pessoas previstas.                          |
| **Métricas do Evento**        | Indicadores numéricos do evento (ex: `PLANNED_HEADCOUNT` para pessoas previstas, `PLANNED_PIECES` para peças).                                                    |

---

## Enumerações e Valores Permitidos

### EventStatus — Status do evento

| Valor         | Descrição                        |
| ------------- | -------------------------------- |
| `DRAFT`       | Rascunho, ainda em edição        |
| `PRE_PLANNED` | Pré-planejado                    |
| `PLANNED`     | Planejado                        |
| `APPROVED`    | Aprovado para execução           |
| `IN_PROGRESS` | Em andamento                     |
| `COMPLETED`   | Concluído                        |
| `CANCELLED`   | Cancelado                        |
| `ADDED`       | Adicionado (inclusão posterior)  |
| `MODIFIED`    | Modificado (alteração posterior) |
| `REMOVED`     | Removido (exclusão posterior)    |

### CollaboratorAvailability — Turno de disponibilidade

| Valor   | Descrição                       |
| ------- | ------------------------------- |
| `DAY`   | Disponível no período diurno    |
| `NIGHT` | Disponível no período noturno   |
| `ALL`   | Disponível em ambos os períodos |

### Weekday — Dias da semana

| Valor       | Descrição     |
| ----------- | ------------- |
| `MONDAY`    | Segunda-feira |
| `TUESDAY`   | Terça-feira   |
| `WEDNESDAY` | Quarta-feira  |
| `THURSDAY`  | Quinta-feira  |
| `FRIDAY`    | Sexta-feira   |
| `SATURDAY`  | Sábado        |
| `SUNDAY`    | Domingo       |

### InventoryTypeType — Tipo de inventário

| Valor   | Descrição                                 |
| ------- | ----------------------------------------- |
| `PAI`   | Tipo principal de inventário              |
| `FILHO` | Tipo secundário vinculado a um evento PAI |

---

## Rotas — Planejamento

### GET `/events`

Lista eventos planejados com filtros avançados. Retorna apenas campos relevantes para escalas.

**Query params:**

| Param               | Tipo   | Descrição                                                                      |
| ------------------- | ------ | ------------------------------------------------------------------------------ |
| `date`              | string | Data específica (`YYYY-MM-DD`)                                                 |
| `dateStart`         | string | Início do período (`YYYY-MM-DD` ou ISO 8601). Sem hora, assume `00:00:00.000Z` |
| `dateEnd`           | string | Fim do período (`YYYY-MM-DD` ou ISO 8601). Sem hora, assume `23:59:59.999Z`    |
| `month`             | string | Mês inteiro (`YYYY-MM`)                                                        |
| `regionId`          | string | ID da regional                                                                 |
| `clientId`          | string | ID do cliente                                                                  |
| `storeId`           | string | ID da loja                                                                     |
| `inventoryTypeId`   | string | ID do tipo de inventário                                                       |
| `inventoryTypeKind` | string | `PAI` ou `FILHO`                                                               |
| `status`            | string | Status separados por vírgula (ex: `PLANNED,CANCELLED,MODIFIED`)                |
| `parentOnly`        | string | `true` para retornar apenas eventos PAI                                        |
| `page`              | int    | Página                                                                         |
| `perPage`           | int    | Itens por página                                                               |

**Exemplo — eventos planejados de março/2026, apenas PAI:**

```bash
curl -H "X-API-Key: ipk_sua_chave" \
  "https://dab41miq8jzsq.cloudfront.net/api/integration/v1/events?month=2026-03&parentOnly=true&status=PLANNED,CANCELLED,MODIFIED"
```

> Para consultar apenas um dia específico, use `date=YYYY-MM-DD` ou envie `dateStart` e `dateEnd` com a mesma data. Nesse caso, a API considera o dia inteiro.

**Exemplo de resposta:**

```json
{
  "data": {
    "items": [
      {
        "id": "cmmkvw8gp000ok401w3rllj3m",
        "status": "PLANNED",
        "plannedAt": "2026-03-01T12:00:00.000Z",
        "plannedPieces": 260000,
        "notes": "DIURNO",
        "parentEventId": null,
        "storeId": "cmmjji6v5001tph01dmx6ueev",
        "meetingPointId": null,
        "inventoryTypeId": "cmmjkbsq00209ph01lfx11las",
        "importData": {
          "endereco": "RUA EXEMPLO, 123",
          "bairro": "CENTRO",
          "cidade": "SÃO PAULO",
          "cep": "05876040",
          "regional": "SP SUL",
          "pessoasPrevistas": 12,
          "horarioInicio": "22:00",
          "lider": "MARIA GESTORA"
        },
        "importKey": "BSA25|2026-03-01",
        "importRevision": "MAR-2026",
        "metrics": [
          { "metric": "PLANNED_HEADCOUNT", "value": 12 },
          { "metric": "PLANNED_PIECES", "value": 260000 }
        ],
        "createdAt": "2026-03-10T17:28:37.081Z",
        "updatedAt": "2026-03-19T20:41:04.097Z",
        "store": {
          "id": "cmmjji6v5001tph01dmx6ueev",
          "code": "BSA25",
          "storeNumber": "25",
          "name": "BSA",
          "nickname": "BARBOSA SUPERMERCADOS",
          "cnpj": "60437647003475",
          "address": null,
          "city": "SÃO PAULO",
          "state": "SP",
          "zipCode": "05876040",
          "client": {
            "id": "cmmjht39u000lph01y22it1z8",
            "corporateName": "SILVA E BARBOSA COMERCIO DE ALIMENTOS LTDA",
            "tradeName": "SILVA E BARBOSA COMERCIO DE ALIMENTOS LTDA",
            "segmentId": "cmmjgtoia0007ph015my20o85"
          },
          "regional": {
            "id": "cmmjitvx90019ph014bzhjevv",
            "name": "SP SUL",
            "state": "SP"
          }
        },
        "meetingPoint": null,
        "inventoryType": {
          "id": "cmmjkbsq00209ph01lfx11las",
          "name": "INVENTÁRIO OFICIAL",
          "code": "T",
          "type": "PAI",
          "description": "EVENTO DE INVENTÁRIO OFICIAL TOTAL"
        },
        "parentEvent": null,
        "children": [
          {
            "id": "cmmxxtwzv05lkpj01szar6k6g",
            "status": "PLANNED",
            "plannedAt": "2026-02-28T11:00:00.000Z",
            "plannedPieces": null,
            "notes": null,
            "importData": {
              "horarioInicio": "11:00"
            },
            "metrics": [],
            "inventoryType": {
              "id": "cmmjk2cw801zqph019bo56xq1",
              "name": "FOLGA",
              "code": "F",
              "type": "FILHO",
              "description": "FOLGA DE EQUIPE"
            },
            "store": {
              "id": "cmmjji6v5001tph01dmx6ueev",
              "name": "BSA",
              "code": "BSA25",
              "city": "SÃO PAULO",
              "state": "SP",
              "zipCode": "05876040"
            }
          }
        ],
        "team": [],
        "orders": []
      }
    ],
    "meta": {
      "page": 1,
      "perPage": 20,
      "total": 89,
      "pageCount": 5
    }
  }
}
```

**Campos retornados no evento:**

| Campo            | Descrição                                                                                                                                                                                                                                          |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`             | Identificador único                                                                                                                                                                                                                                |
| `status`         | Status atual (ver [enumerações](#eventstatus--status-do-evento))                                                                                                                                                                                   |
| `plannedAt`      | Data/hora planejada (ISO 8601)                                                                                                                                                                                                                     |
| `plannedPieces`  | Número estimado de peças a inventariar                                                                                                                                                                                                             |
| `notes`          | Observações (ex: "DIURNO", "NOTURNO")                                                                                                                                                                                                              |
| `parentEventId`  | ID do evento PAI (null se for PAI)                                                                                                                                                                                                                 |
| `importData`     | Dados da planilha de importação (JSON). Contém `endereco`, `bairro`, `cidade`, `cep`, `regional`, `pessoasPrevistas`, `horarioInicio`, `lider`, entre outros campos que variam conforme a planilha. Pode ser `null` se o evento não foi importado. |
| `importKey`      | Chave única de importação (ex: `"BSA25\|2026-03-01"`)                                                                                                                                                                                              |
| `importRevision` | Revisão da importação (ex: `"MAR-2026"`)                                                                                                                                                                                                           |
| `metrics`        | Array de métricas do evento. Cada item tem `metric` (nome) e `value` (valor numérico). Métricas comuns: `PLANNED_HEADCOUNT` (pessoas previstas), `PLANNED_PIECES` (peças previstas).                                                               |
| `store`          | Loja com cliente e regional aninhados                                                                                                                                                                                                              |
| `inventoryType`  | Tipo de inventário (nome, código, PAI/FILHO)                                                                                                                                                                                                       |
| `meetingPoint`   | Ponto de encontro (quando aplicável)                                                                                                                                                                                                               |
| `parentEvent`    | Resumo do evento PAI (quando FILHO)                                                                                                                                                                                                                |
| `children`       | Lista de eventos FILHO (quando PAI). Cada filho inclui `importData`, `metrics` e loja com `city`, `state`, `zipCode`.                                                                                                                              |
| `team`           | Equipe atribuída ao evento                                                                                                                                                                                                                         |
| `orders`         | Ordens de serviço vinculadas                                                                                                                                                                                                                       |

### GET `/events/:id`

Retorna um evento pelo ID com a mesma estrutura da listagem.

### GET `/events/:id/children`

Retorna os eventos FILHO de um evento PAI específico.

```bash
curl -H "X-API-Key: ipk_sua_chave" \
  "https://dab41miq8jzsq.cloudfront.net/api/integration/v1/events/cmmkvw8gp000ok401w3rllj3m/children"
```

---

## Rotas — Colaboradores

### GET `/collaborators`

Lista colaboradores elegíveis para escalas. Retorna dados pessoais, profissão principal, `workFunctions`, classificação, vínculo, disponibilidade, supervisor, dados bancários e **composição de valor** (`valueComposition`).

**Query params:**

| Param               | Tipo   | Descrição                                                       |
| ------------------- | ------ | --------------------------------------------------------------- |
| `search`            | string | Busca no nome, nome social, CPF ou email (min 2 caracteres)     |
| `regionalId`        | string | Filtrar por regional                                            |
| `companyId`         | string | Filtrar por empresa                                             |
| `professionId`      | string | Filtrar pela profissão principal do colaborador                 |
| `classificationId`  | string | Filtrar por classificação                                       |
| `employmentTypeId`  | string | Filtrar por tipo de vínculo                                     |
| `workFunctionIds`   | string | Filtrar por uma ou mais funções, separadas por vírgula          |
| `statusId`          | string | Filtrar por um status específico dentro do conjunto já elegível |
| `availability`      | string | Turno: `DAY`, `NIGHT` ou `ALL`                                  |
| `availableWeekdays` | string | Dias da semana separados por vírgula (ex: `MONDAY,WEDNESDAY`)   |
| `isSporadic`        | string | `true` para avulsos, `false` para fixos                         |
| `supervisorId`      | string | Filtrar por supervisor (ID do colaborador)                      |
| `page`              | int    | Página                                                          |
| `perPage`           | int    | Itens por página                                                |

**Regra fixa desta rota:**

- sempre retorna apenas colaboradores com `status.isActiveState = true`
- o filtro `statusId` restringe ainda mais o conjunto já elegível
- o filtro `workFunctionIds` usa semântica **OR**: retorna colaboradores que possuam ao menos uma das funções informadas

**Exemplo — colaboradores elegíveis da regional SP SUL:**

```bash
curl -H "X-API-Key: ipk_sua_chave" \
  "https://dab41miq8jzsq.cloudfront.net/api/integration/v1/collaborators?regionalId=cmmjitvx90019ph014bzhjevv&perPage=5"
```

**Exemplo — colaboradores com qualquer uma entre duas funções:**

```bash
curl -H "X-API-Key: ipk_sua_chave" \
  "https://dab41miq8jzsq.cloudfront.net/api/integration/v1/collaborators?workFunctionIds=wf-auditoria,wf-treinamento&perPage=5"
```

**Exemplo de resposta:**

```json
{
  "data": {
    "items": [
      {
        "id": "collab-1",
        "fullName": "JOÃO DA SILVA",
        "socialName": null,
        "documentCpf": "12345678901",
        "documentRg": "123456789",
        "birthDate": "1990-05-15T00:00:00.000Z",
        "phone": "1133334444",
        "phoneCountryCode": "55",
        "mobile": "11999998888",
        "mobileCountryCode": "55",
        "email": "joao@email.com",
        "contactEmail": null,
        "addressDistrict": "CENTRO",
        "addressCity": "SÃO PAULO",
        "addressState": "SP",
        "addressZipCode": "01001000",
        "availability": "ALL",
        "availableWeekdays": ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"],
        "isSporadic": false,
        "adhesionDate": "2024-01-15T00:00:00.000Z",
        "departureDate": null,
        "notes": null,
        "createdAt": "2026-03-09T17:00:00.000Z",
        "updatedAt": "2026-03-09T17:00:00.000Z",
        "regional": { "id": "cmmjitvx90019ph014bzhjevv", "name": "SP SUL", "state": "SP" },
        "company": {
          "id": "company-1",
          "corporateName": "EMPRESA LTDA",
          "tradeName": "EMPRESA",
          "cnpj": "12345678000199"
        },
        "profession": { "id": "prof-conferente", "name": "CONFERENTE", "hierarchy": 1 },
        "workFunctions": [
          { "id": "wf-auditoria", "name": "AUDITORIA" },
          { "id": "wf-treinamento", "name": "TREINAMENTO" }
        ],
        "classification": { "id": "class-a", "name": "CLASSE A", "bonusValue": 50.0 },
        "employmentType": { "id": "emp-clt", "name": "CLT", "code": "CLT" },
        "status": { "id": "status-ativo", "name": "ATIVO", "slug": "ativo", "isActiveState": true },
        "statusReason": null,
        "supervisor": {
          "id": "collab-gestor-1",
          "fullName": "MARIA GESTORA",
          "profession": { "id": "prof-gestor", "name": "GESTOR" }
        },
        "bankAccounts": [
          {
            "id": "bank-1",
            "type": "CONTA_CORRENTE",
            "bankCode": "001",
            "bankName": "BANCO DO BRASIL",
            "agencyNumber": "1234",
            "agencyDigit": "5",
            "accountNumber": "12345678",
            "accountDigit": "9",
            "pixKey": "12345678901"
          }
        ],
        "valueComposition": {
          "professionRate": { "amount": 150.0, "currency": "BRL", "profession": "CONFERENTE" },
          "classificationBonus": { "amount": 50.0, "classification": "CLASSE A" },
          "regionalBenefits": [
            { "name": "Vale Transporte", "amount": 20.0, "currency": "BRL" },
            { "name": "Vale Alimentação", "amount": 30.0, "currency": "BRL" }
          ],
          "totalEstimated": 250.0,
          "currency": "BRL"
        }
      }
    ],
    "meta": { "page": 1, "perPage": 5, "total": 150, "pageCount": 30 }
  }
}
```

### GET `/collaborators/sporadic`

Lista conferentes avulsos elegíveis (`isSporadic = true` e `status.isActiveState = true`). Ideal para encontrar pessoas disponíveis sob demanda. Retorna os mesmos campos da listagem principal, incluindo dados bancários e **composição de valor** (`valueComposition`).

**Query params:**

| Param               | Tipo   | Descrição                                              |
| ------------------- | ------ | ------------------------------------------------------ |
| `regionalId`        | string | Filtrar por regional                                   |
| `companyId`         | string | Filtrar por empresa                                    |
| `employmentTypeId`  | string | Filtrar por tipo de vínculo                            |
| `workFunctionIds`   | string | Filtrar por uma ou mais funções, separadas por vírgula |
| `availability`      | string | Turno: `DAY`, `NIGHT` ou `ALL`                         |
| `availableWeekdays` | string | Dias da semana separados por vírgula                   |
| `search`            | string | Busca no nome ou CPF (min 2 caracteres)                |
| `page`              | int    | Página                                                 |
| `perPage`           | int    | Itens por página                                       |

- o filtro `workFunctionIds` usa semântica **OR**: retorna avulsos que possuam ao menos uma das funções informadas

**Exemplo — avulsos da regional SP SUL disponíveis às segundas:**

```bash
curl -H "X-API-Key: ipk_sua_chave" \
  "https://dab41miq8jzsq.cloudfront.net/api/integration/v1/collaborators/sporadic?regionalId=cmmjitvx90019ph014bzhjevv&availableWeekdays=MONDAY"
```

**Exemplo — avulsos com qualquer uma entre duas funções:**

```bash
curl -H "X-API-Key: ipk_sua_chave" \
  "https://dab41miq8jzsq.cloudfront.net/api/integration/v1/collaborators/sporadic?workFunctionIds=wf-auditoria,wf-treinamento&perPage=5"
```

### GET `/collaborators/:id`

Retorna o detalhe completo de um colaborador elegível para escalas, incluindo centro de custo, subordinados diretos, uniforme, dados bancários, lista de `workFunctions` e **composição de valor**.

**Campos adicionais no detalhe (além dos da listagem):**

| Campo               | Descrição                                                                                            |
| ------------------- | ---------------------------------------------------------------------------------------------------- |
| `motherName`        | Nome da mãe                                                                                          |
| `foreignDocument`   | Documento estrangeiro                                                                                |
| `meiCnpj`           | CNPJ MEI                                                                                             |
| `pisNumber`         | Número PIS                                                                                           |
| `addressStreet`     | Rua                                                                                                  |
| `addressNumber`     | Número                                                                                               |
| `addressComplement` | Complemento                                                                                          |
| `addressCountry`    | País                                                                                                 |
| `phoneCountryCode`  | Código de país (DDI) do telefone fixo, só dígitos (ex.: `"55"` para Brasil); `null` se não informado |
| `phoneContactName`  | Nome do contato do telefone fixo                                                                     |
| `mobileCountryCode` | Código de país (DDI) do celular/WhatsApp, só dígitos (ex.: `"55"`)                                   |
| `mobileContactName` | Nome do contato do celular                                                                           |
| `costCenter`        | Centro de custo (`id`, `name`, `code`)                                                               |
| `workFunctions`     | Lista de funções do colaborador (`id`, `name`, `description`, `isActive`)                            |
| `supervisees`       | Lista de subordinados diretos                                                                        |
| `uniform`           | Dados de uniforme                                                                                    |
| `bankAccounts`      | Contas bancárias (ver [dados bancários](#dados-bancários-bankaccounts))                              |
| `valueComposition`  | Composição de valor calculada (ver [composição de valor](#composição-de-valor-valuecomposition))     |

#### Dados bancários (`bankAccounts`)

Presente na listagem, detalhe, esporádicos e equipe. Array de contas bancárias do colaborador.

| Campo           | Tipo           | Descrição                                              |
| --------------- | -------------- | ------------------------------------------------------ |
| `id`            | string         | Identificador da conta                                 |
| `type`          | string         | Tipo da conta (ex: `CONTA_CORRENTE`, `CONTA_POUPANCA`) |
| `bankCode`      | string         | Código do banco (ex: `"001"`)                          |
| `bankName`      | string         | Nome do banco (ex: `"BANCO DO BRASIL"`)                |
| `agencyNumber`  | string         | Número da agência                                      |
| `agencyDigit`   | string \| null | Dígito da agência                                      |
| `accountNumber` | string         | Número da conta                                        |
| `accountDigit`  | string \| null | Dígito da conta                                        |
| `pixKey`        | string \| null | Chave PIX                                              |

#### Composição de valor (`valueComposition`)

Calculada automaticamente e presente em todos os endpoints de colaboradores: listagem (`GET /collaborators`), avulsos (`GET /collaborators/sporadic`) e detalhe (`GET /collaborators/:id`). Também disponível isoladamente via `GET /collaborators/:id/value`.

Combina três fontes de remuneração vinculadas à regional e à **profissão principal** do colaborador (`profession` / `professionId`). A lista `workFunctions` é informativa e não altera o cálculo atual.

| Componente            | Origem                      | Descrição                                                                             |
| --------------------- | --------------------------- | ------------------------------------------------------------------------------------- |
| `professionRate`      | `RegionalProfessionRate`    | Taxa da profissão na regional do colaborador                                          |
| `classificationBonus` | `Classification.bonusValue` | Bonificação pela classificação (ex: Classe A = R$ 50)                                 |
| `regionalBenefits`    | `RegionalBenefit`           | Benefícios ativos da regional (vale transporte, alimentação, etc.)                    |
| `totalEstimated`      | Soma                        | `professionRate.amount + classificationBonus.amount + sum(regionalBenefits[].amount)` |

**Exemplo de `valueComposition` no detalhe:**

```json
{
  "valueComposition": {
    "professionRate": { "amount": 150.0, "currency": "BRL", "profession": "CONFERENTE" },
    "classificationBonus": { "amount": 50.0, "classification": "CLASSE A" },
    "regionalBenefits": [
      { "name": "Vale Transporte", "amount": 20.0, "currency": "BRL" },
      { "name": "Vale Alimentação", "amount": 30.0, "currency": "BRL" }
    ],
    "totalEstimated": 250.0,
    "currency": "BRL"
  }
}
```

> Se o colaborador não tiver regional ou profissão principal vinculada, `valueComposition` será `null`.

### GET `/collaborators/:id/value`

Endpoint dedicado que retorna apenas a composição de valor de um colaborador elegível para escalas. Útil quando você já tem os dados básicos e precisa apenas da remuneração estimada.

```bash
curl -H "X-API-Key: ipk_sua_chave" \
  "https://dab41miq8jzsq.cloudfront.net/api/integration/v1/collaborators/collab-1/value"
```

**Exemplo de resposta:**

```json
{
  "data": {
    "collaboratorId": "collab-1",
    "collaboratorName": "JOÃO DA SILVA",
    "regional": { "id": "cmmjitvx90019ph014bzhjevv", "name": "SP SUL" },
    "professionRate": { "amount": 150.0, "currency": "BRL", "profession": "CONFERENTE" },
    "classificationBonus": { "amount": 50.0, "classification": "CLASSE A" },
    "regionalBenefits": [
      { "name": "Vale Transporte", "description": null, "amount": 20.0, "currency": "BRL" },
      {
        "name": "Vale Alimentação",
        "description": "Ticket para alimentação diária",
        "amount": 30.0,
        "currency": "BRL"
      }
    ],
    "totalEstimated": 250.0,
    "currency": "BRL"
  }
}
```

> Se o colaborador não possuir regional ou profissão vinculada, os campos `professionRate`, `classificationBonus` e `regionalBenefits` retornarão `null`, `null` e `[]` respectivamente, com `totalEstimated = 0` e um campo `note` explicativo.

### GET `/collaborators/:id/team`

Retorna o colaborador com toda a sua árvore de subordinados elegíveis (até 5 níveis). Use para montar a equipe completa de um gerente, coordenador ou gestor. Cada nó da árvore mantém `profession` como cargo/profissão principal e expõe adicionalmente `workFunctions`.

**Exemplo — equipe de um gerente:**

```bash
curl -H "X-API-Key: ipk_sua_chave" \
  "https://dab41miq8jzsq.cloudfront.net/api/integration/v1/collaborators/collab-gerente-1/team"
```

**Exemplo de resposta:**

```json
{
  "data": {
    "id": "collab-gerente-1",
    "fullName": "JOSÉ GERENTE",
    "phone": "1133331111",
    "phoneCountryCode": "55",
    "mobile": "11999991111",
    "mobileCountryCode": "55",
    "email": "jose@email.com",
    "addressCity": "SÃO PAULO",
    "addressState": "SP",
    "availability": "ALL",
    "availableWeekdays": ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"],
    "isSporadic": false,
    "profession": { "id": "prof-gerente", "name": "GERENTE", "hierarchy": 4 },
    "workFunctions": [
      { "id": "wf-lideranca", "name": "LIDERANÇA" },
      { "id": "wf-planejamento", "name": "PLANEJAMENTO OPERACIONAL" }
    ],
    "regional": { "id": "cmmjitvx90019ph014bzhjevv", "name": "SP SUL", "state": "SP" },
    "classification": { "id": "class-a", "name": "CLASSE A" },
    "company": { "id": "company-1", "corporateName": "EMPRESA LTDA" },
    "status": { "id": "status-ativo", "name": "ATIVO", "isActiveState": true },
    "bankAccounts": [
      {
        "id": "bank-1",
        "type": "CONTA_CORRENTE",
        "bankCode": "001",
        "bankName": "BANCO DO BRASIL",
        "agencyNumber": "1234",
        "agencyDigit": "5",
        "accountNumber": "12345678",
        "accountDigit": "9",
        "pixKey": null
      }
    ],
    "supervisees": [
      {
        "id": "collab-coord-1",
        "fullName": "ANA COORDENADORA",
        "profession": { "id": "prof-coordenador", "name": "COORDENADOR", "hierarchy": 3 },
        "workFunctions": [{ "id": "wf-lideranca", "name": "LIDERANÇA" }],
        "regional": { "id": "cmmjitvx90019ph014bzhjevv", "name": "SP SUL", "state": "SP" },
        "status": { "id": "status-ativo", "name": "ATIVO", "isActiveState": true },
        "bankAccounts": [],
        "supervisees": [
          {
            "id": "collab-gestor-1",
            "fullName": "MARIA GESTORA",
            "profession": { "id": "prof-gestor", "name": "GESTOR", "hierarchy": 2 },
            "workFunctions": [
              { "id": "wf-auditoria", "name": "AUDITORIA" },
              { "id": "wf-treinamento", "name": "TREINAMENTO" }
            ],
            "bankAccounts": [],
            "supervisees": [
              {
                "id": "collab-1",
                "fullName": "JOÃO DA SILVA",
                "profession": { "id": "prof-conferente", "name": "CONFERENTE", "hierarchy": 1 },
                "workFunctions": [
                  { "id": "wf-auditoria", "name": "AUDITORIA" },
                  { "id": "wf-inventario", "name": "INVENTÁRIO CÍCLICO" }
                ],
                "availability": "ALL",
                "availableWeekdays": ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"],
                "bankAccounts": [
                  {
                    "id": "bank-2",
                    "type": "CONTA_CORRENTE",
                    "bankCode": "341",
                    "bankName": "ITAÚ",
                    "agencyNumber": "5678",
                    "agencyDigit": null,
                    "accountNumber": "87654321",
                    "accountDigit": "0",
                    "pixKey": "joao@email.com"
                  }
                ],
                "supervisees": []
              }
            ]
          }
        ]
      }
    ]
  }
}
```

---

## Rotas — Catálogos

Dados de referência agrupados sob `/catalogs/`. Use para mapear IDs retornados em eventos e colaboradores.

### GET `/catalogs/professions`

Lista profissões com hierarquia. Cada profissão pode ter um `parent` (superior) e `children` (subordinadas).

**Query params:** `search`, `page`, `perPage`

**Exemplo de resposta:**

```json
{
  "data": {
    "items": [
      {
        "id": "prof-gerente",
        "name": "GERENTE",
        "description": null,
        "hierarchy": 4,
        "parentId": "prof-diretoria",
        "parent": { "id": "prof-diretoria", "name": "DIRETORIA", "hierarchy": 5 },
        "children": [{ "id": "prof-coordenador", "name": "COORDENADOR", "hierarchy": 3 }]
      }
    ],
    "meta": { "page": 1, "perPage": 20, "total": 8, "pageCount": 1 }
  }
}
```

### GET `/catalogs/professions/:id`

Detalhe de uma profissão por ID.

### GET `/catalogs/work-functions`

Lista o novo cadastro de funções operacionais, separado do cargo/profissão (`profession`) do colaborador.

**Query params:** `search`, `page`, `perPage`

**Exemplo de resposta:**

```json
{
  "data": {
    "items": [
      {
        "id": "wf-auditoria",
        "name": "AUDITORIA",
        "description": "Atuação em auditorias operacionais",
        "isActive": true
      }
    ],
    "meta": { "page": 1, "perPage": 20, "total": 4, "pageCount": 1 }
  }
}
```

### GET `/catalogs/work-functions/:id`

Detalhe de uma função operacional por ID.

### GET `/catalogs/employment-types`

Lista tipos de vínculo. Não paginado.

**Exemplo de resposta:**

```json
{
  "data": [
    { "id": "emp-clt", "name": "CLT", "code": "CLT", "order": 1 },
    { "id": "emp-mei", "name": "MEI", "code": "MEI", "order": 2 }
  ]
}
```

### GET `/catalogs/classifications`

Lista classificações de colaborador com valor de bonificação. Não paginado.

**Exemplo de resposta:**

```json
{
  "data": [
    { "id": "class-a", "name": "CLASSE A", "bonusValue": 50.0 },
    { "id": "class-b", "name": "CLASSE B", "bonusValue": 30.0 }
  ]
}
```

### GET `/catalogs/collaborator-statuses`

Lista status de colaborador com motivos (reasons) aninhados. Não paginado.

O campo `isActiveState` define se aquele status libera ou bloqueia o colaborador para aparecer nas rotas de integração usadas pelo sistema de escalas.

**Exemplo de resposta:**

```json
{
  "data": [
    {
      "id": "status-ativo",
      "name": "ATIVO",
      "slug": "ativo",
      "isActiveState": true,
      "reasons": []
    },
    {
      "id": "status-inativo",
      "name": "INATIVO",
      "slug": "inativo",
      "isActiveState": false,
      "reasons": [{ "id": "reason-1", "name": "DEMISSÃO" }]
    }
  ]
}
```

### GET `/catalogs/companies`

Lista empresas com centros de custo. Paginado.

**Query params:** `search`, `page`, `perPage`

### GET `/catalogs/companies/:id`

Detalhe de uma empresa por ID com centros de custo.

---

## Rotas — Infraestrutura

### GET `/segments`

Lista segmentos de mercado. **Query params:** `search`, `page`, `perPage`

### GET `/segments/:id`

Detalhe de um segmento.

### GET `/regions`

Lista regionais com pontos de encontro. **Query params:** `search`, `state` (UF, 2 caracteres), `page`, `perPage`

### GET `/regions/:id`

Detalhe de uma regional com pontos de encontro.

### GET `/inventory-types`

Lista tipos de inventário. **Query params:** `search`, `type` (`PAI` ou `FILHO`), `page`, `perPage`

### GET `/inventory-types/:id`

Detalhe de um tipo de inventário.

### GET `/clients`

Lista clientes com segmento. **Query params:** `search`, `segmentId`, `page`, `perPage`

### GET `/clients/:id`

Detalhe de um cliente com segmento e lojas.

### GET `/stores`

Lista lojas com cliente e regional. **Query params:** `search`, `clientId`, `regionId`, `page`, `perPage`

### GET `/stores/:id`

Detalhe de uma loja com cliente e regional.

---

## Cenários de Uso

### Montar escala de março/2026

```bash
# 1. Buscar todos os eventos PAI de março
GET /events?month=2026-03&parentOnly=true&status=PLANNED,,,MODIFIED

# 2. Para cada evento, verificar a regional e tipo
#    O campo store.regional mostra a regional responsável
#    O campo inventoryType mostra o tipo de inventário
#    O campo plannedPieces mostra o volume estimado

# 3. Buscar a equipe do gerente responsável pela regional
GET /collaborators?regionalId={regionalId}&professionId={profGerente}
GET /collaborators/{gerenteId}/team

# 4. Se precisar de reforço, buscar avulsos disponíveis
GET /collaborators/sporadic?regionalId={regionalId}&availableWeekdays=MONDAY
```

### Encontrar conferentes disponíveis para um evento específico

```bash
# 1. Verificar detalhes do evento
GET /events/{eventId}
# → Anotar: store.regional.id, plannedAt (dia da semana)

# 2. Buscar conferentes da regional disponíveis naquele dia
GET /collaborators?regionalId={regionalId}&professionId={profConferente}&availableWeekdays=WEDNESDAY&availability=DAY

# 3. Se não houver suficientes, buscar avulsos
GET /collaborators/sporadic?regionalId={regionalId}&availableWeekdays=WEDNESDAY&availability=DAY
```

### Consultar equipe completa de um gerente

```bash
# Retorna o gerente e todos os subordinados recursivamente
GET /collaborators/{gerenteId}/team

# Resposta contém:
# Gerente → Coordenadores → Gestores → Conferentes
# Cada nível com dados de contato, disponibilidade e status
```

### Consultar composição de valor de um colaborador

```bash
# Opção 1 — no detalhe do colaborador (campo valueComposition incluído)
GET /collaborators/{collaboratorId}
# → O campo valueComposition já vem calculado na resposta

# Opção 2 — endpoint dedicado (retorna apenas a composição)
GET /collaborators/{collaboratorId}/value
# → Retorna professionRate, classificationBonus, regionalBenefits e totalEstimated
```

### Listar dados de referência para popular dropdowns

```bash
# Profissões (para filtros)
GET /catalogs/professions

# Classificações (para saber bonificação)
GET /catalogs/classifications

# Tipos de vínculo (CLT, MEI, etc.)
GET /catalogs/employment-types

# Status possíveis
GET /catalogs/collaborator-statuses

# Regionais (para filtros geográficos)
GET /regions
```

---

## Códigos de Erro

| Status | Significado                                                            |
| ------ | ---------------------------------------------------------------------- |
| 400    | Parâmetros inválidos (formato errado, valor fora do esperado)          |
| 401    | API Key ausente ou inválida                                            |
| 403    | API Key desativada ou expirada                                         |
| 404    | Recurso não encontrado                                                 |
| 422    | Erro de validação (campo obrigatório ausente, tipo incorreto)          |
| 429    | Rate limit excedido — aguarde o tempo indicado no header `Retry-After` |
| 500    | Erro interno do servidor                                               |

---

## Headers de Segurança

Todas as respostas incluem headers de segurança aplicados automaticamente:

| Header                      | Valor                                 | Finalidade                              |
| --------------------------- | ------------------------------------- | --------------------------------------- |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | Força HTTPS por 1 ano                   |
| `X-Content-Type-Options`    | `nosniff`                             | Impede MIME sniffing                    |
| `X-Frame-Options`           | `SAMEORIGIN`                          | Impede embedding em iframes externos    |
| `Referrer-Policy`           | `no-referrer`                         | Não envia referrer em requests externos |

### Boas práticas

1. **Sempre use HTTPS** — requisições HTTP são redirecionadas, mas isso adiciona latência desnecessária.
2. **Cachear dados estáveis** — catálogos (`/catalogs/*`), regionais (`/regions`), segmentos (`/segments`) e tipos de inventário (`/inventory-types`) mudam raramente. Cachear por 1-6 horas reduz chamadas significativamente.
3. **Usar `perPage=100`** — para sincronizações em lote, maximize o tamanho de página para reduzir o número total de requisições.
4. **Monitorar rate limit** — use os headers `RateLimit-Remaining` e `RateLimit-Reset` para evitar atingir o limite de 1.000 req/15min.
5. **Implementar retry com backoff** — ao receber 429 ou 5xx, aguarde o `Retry-After` ou use exponential backoff (1s, 2s, 4s, 8s...).

---
