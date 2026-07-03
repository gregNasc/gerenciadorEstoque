# 08 — API_INTERNA

## Objetivo

Este documento define os padrões utilizados pelas APIs internas do Gerenciador de Estoque.

As APIs são responsáveis por fornecer dados para:

* Interface Web;
* Dashboards;
* Componentes dinâmicos;
* Integrações futuras;
* Sistema de Planejamento;
* Aplicativos móveis (caso existam);
* Ferramentas de Business Intelligence.

Este documento representa o contrato funcional das APIs.

---

# Princípios

## APIs representam serviços

Uma API não deve conter regra de negócio.

Ela deve:

* receber parâmetros;
* validar permissões;
* chamar o Service correspondente;
* devolver uma resposta padronizada.

---

## Toda regra permanece nos Services

Fluxo padrão:

```text
Requisição

↓

View/API

↓

Service

↓

Model

↓

Resposta JSON
```

---

## APIs devem ser reutilizáveis

Uma API deve poder ser utilizada por:

* Interface Web;
* Sistema de Planejamento;
* Power BI;
* Aplicativos;
* Integrações futuras.

---

## APIs devem ser consistentes

Todas devem seguir:

* mesmo padrão de URL;
* mesmo padrão de resposta;
* mesmos códigos HTTP;
* mesma estrutura de erros.

---

# Organização

```text
/api/

    estoque/

    insumos/

    inventarios/

    checklists/

    dashboard/

    usuarios/

    notificacoes/
```

---

# Versionamento

Desde o início, todas as APIs deverão prever versionamento.

Exemplo:

```text
/api/v1/
```

Quando houver mudanças incompatíveis:

```text
/api/v2/
```

O versionamento evita quebrar integrações existentes.

---

# Estrutura das Respostas

## Sucesso

```json
{
    "success": true,
    "message": "Operação realizada com sucesso.",
    "data": {}
}
```

---

## Erro

```json
{
    "success": false,
    "message": "Saldo insuficiente.",
    "errors": {}
}
```

---

## Listagens

```json
{
    "success": true,
    "count": 120,
    "next": "...",
    "previous": "...",
    "results": []
}
```

---

# Códigos HTTP

## 200

Operação executada com sucesso.

---

## 201

Registro criado.

---

## 204

Operação realizada sem conteúdo de retorno.

---

## 400

Erro de validação.

---

## 401

Usuário não autenticado.

---

## 403

Usuário autenticado, porém sem permissão.

---

## 404

Registro não encontrado.

---

## 409

Conflito de operação.

Exemplo:

* equipamento indisponível;
* saldo insuficiente;
* checklist já finalizado.

---

## 500

Erro inesperado.

Deve ser evitado.

Sempre registrar logs.

---

# Autenticação

## Atual

Sessão do Django.

---

## Futuro

Preparar suporte para:

* Token;
* JWT;
* API Key;
* OAuth (caso necessário).

---

# APIs do Estoque

## Equipamentos

Permitir:

* listar;
* consultar;
* cadastrar;
* editar;
* alterar status;
* visualizar histórico;
* consultar disponibilidade.

---

## Produtos

Permitir:

* listar;
* consultar;
* filtrar por categoria.

---

## Bases

Permitir:

* listar;
* consultar;
* equipamentos;
* indicadores.

---

## Transferências

Permitir:

* criar;
* aprovar;
* cancelar;
* receber;
* consultar.

---

## Empréstimos

Permitir:

* criar;
* confirmar recebimento;
* confirmar devolução;
* consultar.

---

## SICK

Permitir:

* registrar;
* resolver;
* listar;
* consultar.

---

# APIs dos Insumos

## Categorias

Permitir:

* listar;
* consultar.

---

## Insumos

Permitir:

* listar;
* consultar;
* cadastrar;
* editar;
* alterar preço;
* alterar estoque mínimo.

---

## Movimentações

Permitir:

* entrada;
* saída;
* devolução;
* perda;
* ajuste;
* consulta.

---

## Solicitações

Permitir:

* criar;
* aprovar;
* reprovar;
* colocar em compra;
* finalizar.

---

## Inventários

Permitir:

* listar;
* consultar;
* criar;
* editar;
* finalizar.

---

## Checklists

Permitir:

* criar;
* consultar;
* adicionar equipamentos;
* adicionar insumos;
* adicionar TAGs;
* registrar retorno;
* finalizar.

---

## TAGs

Permitir:

* consultar lotes;
* consultar saldo;
* consultar movimentações;
* consultar custo.

---

## Consumo

Permitir:

* consultar custo;
* consultar consumo;
* consultar perdas.

---

# APIs de Dashboard

## Dashboard Principal

Fornecer:

* KPIs;
* gráficos;
* filtros;
* indicadores.

---

## Dashboard Operacional

Fornecer:

* inventários;
* checklists;
* pendências;
* equipamentos.

---

## Dashboard Compras

Fornecer:

* estoque crítico;
* consumo;
* projeção;
* preços.

---

## Dashboard Planejamento

Fornecer:

* inventários planejados;
* previsão de consumo;
* necessidade futura.

---

## Dashboard Financeiro

Fornecer:

* custos;
* perdas;
* categorias;
* clientes.

---

## Dashboard Executivo

Fornecer:

* custo por cliente;
* custo por base;
* custo por grupo;
* reutilização;
* indicadores estratégicos.

---

# Filtros

Todas as APIs que permitirem listagem devem aceitar filtros quando aplicável.

Principais filtros:

* empresa;
* grupo;
* base;
* cliente;
* categoria;
* produto;
* status;
* período;
* usuário.

---

# Pesquisa

Sempre que fizer sentido:

```text
?q=
```

Exemplo:

```text
?q=coletor
```

---

# Ordenação

Sempre que possível:

```text
?ordering=
```

Exemplo:

```text
?ordering=data_inicio
```

---

# Paginação

Listagens grandes deverão utilizar paginação.

Objetivos:

* melhorar desempenho;
* reduzir tráfego;
* facilitar navegação.

---

# Permissões

Toda API deve validar permissões antes da operação.

A validação deve ocorrer antes da execução do Service.

---

# Auditoria

Operações relevantes devem registrar histórico.

Exemplos:

* alteração de estoque;
* finalização de checklist;
* atualização de preços;
* transferências;
* empréstimos.

---

# Performance

Boas práticas:

* select_related();
* prefetch_related();
* annotate();
* índices;
* cache quando necessário.

Evitar consultas repetitivas.

---

# Integração com Planejamento

O sistema deverá disponibilizar APIs específicas para integração com o sistema de Planejamento.

Essas APIs serão definidas após análise do documento técnico da integração.

Objetivos previstos:

* receber inventários planejados;
* consultar necessidade de recursos;
* consultar consumo previsto;
* sincronizar status.

---

# Integração com Business Intelligence

As APIs deverão permitir consumo por ferramentas de BI.

Indicadores previstos:

* custos;
* consumo;
* inventários;
* equipamentos;
* perdas;
* reutilização;
* estoque;
* TAGs.

---

# APIs Futuras

Planejadas:

* WhatsApp;
* E-mail;
* Notificações Push;
* Portal Executivo;
* Aplicativo móvel.

---

# Convenções

## URLs

Utilizar nomes claros.

Exemplo:

```text
/api/v1/insumos/

/api/v1/inventarios/

/api/v1/dashboard/executivo/
```

Evitar abreviações desnecessárias.

---

## JSON

Todos os campos devem utilizar nomes consistentes.

Preferencialmente:

```text
snake_case
```

---

## Datas

Preferencialmente utilizar formato ISO 8601.

---

## Valores Monetários

Sempre retornar valores numéricos.

A formatação monetária deve ocorrer apenas na interface.

---

# Boas Práticas

As APIs devem ser:

* previsíveis;
* consistentes;
* reutilizáveis;
* documentadas;
* performáticas;
* seguras.

---

# Objetivo da Fase 2

Ao final da Fase 2, todas as integrações internas do sistema deverão utilizar APIs padronizadas.

Os Services continuarão concentrando toda a regra de negócio.

As APIs serão responsáveis apenas pela comunicação entre consumidores e a camada de negócio.

---

# Conclusão

A API Interna do Gerenciador de Estoque deve funcionar como uma camada estável de comunicação entre o núcleo do sistema e qualquer consumidor de dados.

Seu papel é garantir consistência, segurança, desempenho e facilidade de integração, preservando a arquitetura baseada em Services e permitindo que o sistema evolua sem quebrar consumidores existentes.
