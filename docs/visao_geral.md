# 01 — Visão Geral do Projeto

## Gerenciador de Estoque

O Gerenciador de Estoque é um sistema web desenvolvido em Django para controlar equipamentos, insumos, inventários, movimentações operacionais, checklists, custos e indicadores gerenciais.

O projeto nasceu como um controle de estoque de equipamentos por base, mas evoluiu para uma plataforma operacional mais ampla, capaz de apoiar áreas como Operação, Compras, Planejamento, Financeiro e Diretoria.

---

## Objetivo do Sistema

O objetivo principal do sistema é centralizar e organizar informações operacionais relacionadas a:

* equipamentos;
* bases;
* usuários;
* transferências;
* empréstimos;
* itens em SICK;
* insumos;
* inventários;
* checklists;
* consumo;
* custos;
* comunicados;
* dashboards;
* indicadores executivos.

O sistema deve reduzir controles paralelos em planilhas, melhorar a rastreabilidade das movimentações e fornecer dados confiáveis para tomada de decisão.

---

## Filosofia do Projeto

O sistema deve seguir alguns princípios fundamentais:

1. **A operação vem antes do código.**
   Toda funcionalidade deve representar uma necessidade real da operação.

2. **Não quebrar o que já funciona.**
   Refatorações devem ser incrementais e seguras.

3. **Regras de negócio devem ficar centralizadas.**
   Sempre que possível, regras críticas devem ficar em services, não espalhadas por views ou templates.

4. **A interface deve ser simples para quem opera.**
   Mesmo com dashboards avançados, o uso diário precisa continuar fácil.

5. **Os dados devem gerar análise.**
   O sistema não deve apenas registrar movimentações, mas também responder perguntas gerenciais.

6. **Documentação é parte do produto.**
   Toda decisão importante deve ser registrada nos documentos do projeto.

---

## Módulos Principais

### Estoque

Responsável pelo controle de equipamentos físicos, incluindo:

* coletores;
* impressoras;
* notebooks;
* routers;
* patrimônio;
* número de série;
* base atual;
* status;
* histórico;
* transferências;
* empréstimos;
* itens em SICK.

---

### Insumos

Responsável pelo controle de materiais consumíveis, reutilizáveis e controlados por lote, incluindo:

* TAGs;
* sulfite;
* durex;
* máscaras;
* luvas;
* toucas;
* materiais operacionais;
* entradas;
* saídas;
* devoluções;
* perdas;
* ajustes;
* custo médio;
* estoque mínimo;
* estoque máximo.

---

### Inventários

Representam operações realizadas para clientes, lojas e bases.

Cada inventário pode gerar:

* checklist;
* envio de equipamentos;
* envio de insumos;
* controle de TAGs;
* consumo;
* devoluções;
* perdas;
* custo final individual.

---

### Checklist

O checklist operacional é uma das peças centrais do sistema.

Ele deve permitir registrar:

* cliente;
* loja;
* base;
* equipamentos enviados;
* equipamentos retornados;
* insumos enviados;
* insumos utilizados;
* insumos retornados;
* insumos perdidos;
* TAGs enviadas;
* TAGs retornadas;
* custo final do inventário.

---

### Compras

A área de Compras deve poder:

* cadastrar novos insumos;
* atualizar preços;
* definir estoque mínimo;
* definir parâmetros de reposição;
* visualizar estoque baixo;
* acompanhar consumo por período;
* acompanhar projeção de compras.

---

### Planejamento

A área de Planejamento deverá utilizar o sistema para:

* acompanhar inventários;
* prever demanda operacional;
* consultar consumo previsto;
* visualizar necessidade de insumos;
* integrar futuramente com outro sistema via API.

---

### Executivo / Diretoria

A visão executiva deve ser gerencial e orientada a indicadores.

Deve responder perguntas como:

* quanto custa cada inventário;
* quanto custa cada cliente;
* quanto custa cada base;
* quanto custa cada grupo de bases;
* qual é o custo médio por inventário;
* quais categorias mais consomem recursos;
* onde há perda;
* onde há desperdício;
* quanto é reutilizado;
* qual é a projeção de compras.

---

## Conceitos Importantes

### Base

Representa uma unidade operacional onde há estoque, equipamentos, usuários e inventários.

---

### Grupo de Bases

Representa o agrupamento de várias bases.

Indicadores gerenciais devem diferenciar:

* custo por base;
* custo por grupo.

Não usar "regional" como sinônimo de grupo sem validação.

---

### Cliente

Representa o cliente do inventário, normalmente identificado por sigla.

Exemplos:

* OXX;
* PDA;
* EXS.

---

### Insumo Consumível

Material que, uma vez utilizado, deve ser baixado do estoque.

Exemplos:

* máscara;
* luva;
* touca;
* sulfite;
* TAG.

---

### Insumo Reutilizável

Material que pode ser enviado para um inventário e retornar para uso futuro.

Exemplos:

* durex;
* balança;
* escada;
* botas;
* transformadores.

O custo só deve ser apropriado quando o item for efetivamente consumido, perdido ou descartado.

---

### TAGs

As TAGs possuem tratamento especial.

Elas são compradas por rolo, normalmente com 1000 unidades.

O custo unitário da TAG deve ser calculado assim:

```text
valor_do_rolo / quantidade_de_tags_do_rolo
```

Exemplo:

```text
R$ 18,00 / 1000 = R$ 0,018 por TAG
```

Se forem utilizadas as TAGs de 5000 até 5345, o consumo é inclusivo:

```text
5345 - 5000 + 1 = 346 TAGs
```

Custo:

```text
346 × 0,018 = R$ 6,228
```

Valor arredondado:

```text
R$ 6,23
```

---

## Fase 2 do Projeto

A Fase 2 tem como objetivo transformar o sistema em um produto mais profissional, documentado, modular e preparado para expansão.

As principais frentes são:

1. documentação oficial;
2. refatoração módulo por módulo;
3. melhoria dos cadastros;
4. melhoria do fluxo de SICK;
5. evolução dos comunicados/notificações;
6. melhoria do dashboard principal;
7. criação dos painéis de Compras, Planejamento e Executivo;
8. internacionalização para português e espanhol;
9. preparação para integrações via API;
10. futura migração de infraestrutura;
11. redesign visual inspirado em Power BI.

---

## Regra de Evolução

A partir da Fase 2, toda funcionalidade importante deve seguir este fluxo:

```text
Ideia
↓
Discussão
↓
Documentação
↓
Validação
↓
Implementação
↓
Teste
↓
Deploy
```

Nenhuma funcionalidade relevante deve ser implementada sem que sua regra de negócio esteja clara e registrada.

---

## Direção do Produto

O sistema deve evoluir de um controle operacional para uma plataforma de gestão.

Ele deve atender três níveis:

### Operacional

Usuários que executam ações no dia a dia:

* cadastrar equipamentos;
* movimentar estoque;
* abrir checklists;
* registrar consumo;
* marcar SICK;
* receber e devolver equipamentos.

### Gerencial

Usuários que acompanham e coordenam:

* gestores;
* compras;
* planejamento;
* financeiro.

### Executivo

Usuários que precisam de indicadores consolidados:

* diretoria;
* gerência geral;
* financeiro estratégico.

---

## Visão de Longo Prazo

O Gerenciador de Estoque deve se tornar uma plataforma capaz de:

* controlar equipamentos;
* controlar insumos;
* medir custos operacionais;
* reduzir desperdícios;
* apoiar compras;
* apoiar planejamento;
* gerar indicadores executivos;
* integrar com sistemas externos;
* fornecer dados confiáveis para decisões estratégicas.

O objetivo final não é apenas ter um sistema que funciona, mas um produto sólido, bem estruturado, fácil de manter e alinhado à realidade da operação.
