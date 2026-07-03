# 09 — Permissões

## Objetivo

Este documento define a lógica de permissões do Gerenciador de Estoque.

A finalidade é deixar claro quem pode visualizar, cadastrar, editar, aprovar, movimentar, finalizar e consultar informações em cada módulo do sistema.

---

# 1. Princípios

## Menor privilégio necessário

Cada usuário deve ter acesso apenas ao que precisa para executar sua função.

---

## Permissão por perfil e por base

O acesso deve considerar:

* perfil do usuário;
* bases vinculadas ao usuário;
* grupo de bases, quando aplicável;
* permissões específicas do Django.

---

## Operação protegida

A interface pode esconder botões, mas a segurança real deve estar nas views, APIs e services.

---

## Auditoria

Toda ação crítica deve registrar usuário, data e contexto.

---

# 2. Perfis Principais

## Administrador

Acesso amplo ao sistema.

Pode:

* gerenciar usuários;
* gerenciar permissões;
* acessar todas as bases;
* acessar todos os dashboards;
* corrigir cadastros;
* operar fluxos administrativos;
* consultar auditorias.

---

## Gestor

Usuário com responsabilidade sobre uma ou mais bases.

Pode:

* visualizar estoque das bases vinculadas;
* solicitar transferências;
* receber equipamentos;
* acompanhar SICK;
* visualizar dashboards operacionais;
* acompanhar inventários;
* acompanhar checklists;
* consultar históricos.

---

## Operador

Usuário operacional.

Pode:

* cadastrar equipamentos quando permitido;
* consultar estoque da própria base;
* abrir ou preencher checklist;
* registrar retorno;
* marcar SICK;
* consultar dados operacionais permitidos.

---

## Compras

Usuário responsável pelos insumos sob ponto de vista de aquisição.

Pode:

* cadastrar insumos;
* atualizar preços;
* definir estoque mínimo;
* definir estoque máximo;
* consultar estoque crítico;
* visualizar projeção de compras;
* acompanhar consumo;
* acessar dashboard de Compras.

---

## Planejamento

Usuário responsável pela visão futura da operação.

Pode:

* visualizar inventários planejados;
* visualizar demanda futura;
* consultar necessidade de recursos;
* consultar consumo previsto;
* acessar dashboard de Planejamento;
* acompanhar integração futura via API.

---

## Financeiro

Usuário responsável por custos e análises financeiras.

Pode:

* visualizar custos;
* consultar consumo;
* consultar perdas;
* consultar custo por inventário;
* consultar custo por cliente;
* consultar custo por base;
* consultar custo por grupo;
* acessar dashboard Financeiro.

---

## Executivo

Usuário responsável por visão estratégica.

Pode:

* visualizar indicadores consolidados;
* consultar dashboards executivos;
* acompanhar custos;
* acompanhar perdas;
* acompanhar reutilização;
* acompanhar projeções;
* visualizar indicadores por cliente, base e grupo.

---

# 3. Permissões por Módulo

## 3.1 Usuários

| Ação                    | Admin | Gestor   | Operador | Compras | Planejamento | Financeiro | Executivo |
| ----------------------- | ----- | -------- | -------- | ------- | ------------ | ---------- | --------- |
| Cadastrar usuário       | Sim   | Não      | Não      | Não     | Não          | Não        | Não       |
| Editar usuário          | Sim   | Não      | Não      | Não     | Não          | Não        | Não       |
| Alterar perfil          | Sim   | Não      | Não      | Não     | Não          | Não        | Não       |
| Vincular bases          | Sim   | Não      | Não      | Não     | Não          | Não        | Não       |
| Ativar/inativar usuário | Sim   | Não      | Não      | Não     | Não          | Não        | Não       |
| Visualizar usuários     | Sim   | Limitado | Não      | Não     | Não          | Não        | Não       |

---

## 3.2 Equipamentos

| Ação                   | Admin  | Gestor              | Operador               |
| ---------------------- | ------ | ------------------- | ---------------------- |
| Cadastrar equipamento  | Sim    | Sim, se permitido   | Sim, se permitido      |
| Editar equipamento     | Sim    | Limitado à base     | Limitado, se permitido |
| Visualizar equipamento | Sim    | Bases vinculadas    | Base vinculada         |
| Alterar status         | Sim    | Sim, conforme regra | Limitado               |
| Consultar histórico    | Sim    | Bases vinculadas    | Base vinculada         |
| Excluir equipamento    | Evitar | Não                 | Não                    |

Exclusão deve ser evitada. Preferir baixa ou inativação.

---

## 3.3 SICK

| Ação                | Admin | Gestor           | Operador               |
| ------------------- | ----- | ---------------- | ---------------------- |
| Marcar SICK         | Sim   | Sim              | Sim                    |
| Resolver SICK       | Sim   | Sim              | Limitado, se permitido |
| Visualizar SICK     | Sim   | Bases vinculadas | Base vinculada         |
| Editar observação   | Sim   | Sim              | Limitado               |
| Consultar histórico | Sim   | Sim              | Sim                    |

---

## 3.4 Transferências

| Ação                      | Admin | Gestor           | Operador |
| ------------------------- | ----- | ---------------- | -------- |
| Solicitar transferência   | Sim   | Sim              | Não      |
| Aprovar transferência     | Sim   | Conforme regra   | Não      |
| Enviar equipamento        | Sim   | Conforme regra   | Não      |
| Receber equipamento       | Sim   | Sim              | Não      |
| Cancelar transferência    | Sim   | Conforme regra   | Não      |
| Visualizar transferências | Sim   | Bases vinculadas | Limitado |

---

## 3.5 Empréstimos

| Ação                   | Admin | Gestor           | Operador |
| ---------------------- | ----- | ---------------- | -------- |
| Criar empréstimo       | Sim   | Sim              | Não      |
| Confirmar recebimento  | Sim   | Sim              | Não      |
| Solicitar devolução    | Sim   | Sim              | Não      |
| Confirmar devolução    | Sim   | Sim              | Não      |
| Visualizar empréstimos | Sim   | Bases vinculadas | Limitado |

---

# 4. Permissões do Módulo Insumos

## 4.1 Cadastro de Insumos

| Ação                    | Admin | Compras | Gestor | Operador |
| ----------------------- | ----- | ------- | ------ | -------- |
| Cadastrar novo insumo   | Sim   | Sim     | Não    | Não      |
| Editar descrição        | Sim   | Sim     | Não    | Não      |
| Editar categoria        | Sim   | Sim     | Não    | Não      |
| Editar tipo de controle | Sim   | Sim     | Não    | Não      |
| Ativar/inativar insumo  | Sim   | Sim     | Não    | Não      |
| Visualizar insumos      | Sim   | Sim     | Sim    | Sim      |

---

## 4.2 Preços e Estoque Mínimo

| Ação                   | Admin | Compras | Financeiro | Gestor             | Operador |
| ---------------------- | ----- | ------- | ---------- | ------------------ | -------- |
| Atualizar preço        | Sim   | Sim     | Não        | Não                | Não      |
| Visualizar preço       | Sim   | Sim     | Sim        | Conforme permissão | Não      |
| Definir estoque mínimo | Sim   | Sim     | Não        | Não                | Não      |
| Definir estoque máximo | Sim   | Sim     | Não        | Não                | Não      |
| Ver estoque crítico    | Sim   | Sim     | Sim        | Sim                | Limitado |

---

## 4.3 Movimentações de Insumos

| Ação             | Admin | Compras | Gestor            | Operador          |
| ---------------- | ----- | ------- | ----------------- | ----------------- |
| Entrada          | Sim   | Sim     | Sim, se permitido | Sim, se permitido |
| Saída            | Sim   | Não     | Sim               | Sim, se permitido |
| Devolução        | Sim   | Não     | Sim               | Sim, se permitido |
| Perda            | Sim   | Não     | Sim               | Sim, se permitido |
| Ajuste           | Sim   | Sim     | Sim, se permitido | Não               |
| Visualizar saldo | Sim   | Sim     | Bases vinculadas  | Base vinculada    |

---

## 4.4 Solicitações de Insumos

| Ação                    | Admin | Compras        | Gestor            | Operador          |
| ----------------------- | ----- | -------------- | ----------------- | ----------------- |
| Criar solicitação       | Sim   | Sim            | Sim               | Sim, se permitido |
| Aprovar solicitação     | Sim   | Conforme regra | Sim, se permitido | Não               |
| Reprovar solicitação    | Sim   | Conforme regra | Sim, se permitido | Não               |
| Colocar em compra       | Sim   | Sim            | Não               | Não               |
| Finalizar solicitação   | Sim   | Sim            | Não               | Não               |
| Visualizar solicitações | Sim   | Sim            | Bases vinculadas  | Base vinculada    |

---

# 5. Inventários e Checklists

## 5.1 Inventários

| Ação                  | Admin     | Planejamento | Gestor                | Operador       |
| --------------------- | --------- | ------------ | --------------------- | -------------- |
| Criar inventário      | Sim       | Sim          | Sim                   | Não            |
| Editar inventário     | Sim       | Sim          | Sim, bases vinculadas | Não            |
| Finalizar inventário  | Sim       | Sim          | Sim                   | Não            |
| Visualizar inventário | Sim       | Sim          | Bases vinculadas      | Base vinculada |
| Integrar via API      | Planejado | Planejado    | Não                   | Não            |

---

## 5.2 Checklists

| Ação                  | Admin | Gestor            | Operador          |
| --------------------- | ----- | ----------------- | ----------------- |
| Criar checklist       | Sim   | Sim               | Sim, se permitido |
| Adicionar equipamento | Sim   | Sim               | Sim               |
| Adicionar insumo      | Sim   | Sim               | Sim               |
| Adicionar TAG         | Sim   | Sim               | Sim               |
| Registrar retorno     | Sim   | Sim               | Sim               |
| Registrar perda       | Sim   | Sim               | Sim, se permitido |
| Finalizar checklist   | Sim   | Sim               | Sim, se permitido |
| Reabrir checklist     | Sim   | Sim, se permitido | Não               |

---

## 5.3 TAGs

| Ação              | Admin | Compras | Gestor            | Operador          |
| ----------------- | ----- | ------- | ----------------- | ----------------- |
| Cadastrar lote    | Sim   | Sim     | Não               | Não               |
| Editar lote       | Sim   | Sim     | Não               | Não               |
| Visualizar lote   | Sim   | Sim     | Bases vinculadas  | Base vinculada    |
| Enviar faixa      | Sim   | Não     | Sim               | Sim               |
| Registrar retorno | Sim   | Não     | Sim               | Sim               |
| Registrar perda   | Sim   | Não     | Sim               | Sim, se permitido |
| Consultar custo   | Sim   | Sim     | Sim, se permitido | Não               |

---

# 6. Custos e Dashboards

## 6.1 Visualização de Custos

| Informação           | Admin | Compras | Planejamento | Financeiro | Executivo | Gestor             | Operador |
| -------------------- | ----- | ------- | ------------ | ---------- | --------- | ------------------ | -------- |
| Custo por inventário | Sim   | Sim     | Sim          | Sim        | Sim       | Conforme permissão | Não      |
| Custo por cliente    | Sim   | Sim     | Sim          | Sim        | Sim       | Não                | Não      |
| Custo por base       | Sim   | Sim     | Sim          | Sim        | Sim       | Limitado           | Não      |
| Custo por grupo      | Sim   | Sim     | Sim          | Sim        | Sim       | Não                | Não      |
| Preço unitário       | Sim   | Sim     | Não          | Sim        | Sim       | Conforme regra     | Não      |
| Perdas               | Sim   | Sim     | Sim          | Sim        | Sim       | Sim                | Limitado |
| Reutilização         | Sim   | Sim     | Sim          | Sim        | Sim       | Sim                | Limitado |

---

## 6.2 Acesso aos Dashboards

| Dashboard    | Admin | Gestor | Operador      | Compras | Planejamento  | Financeiro    | Executivo     |
| ------------ | ----- | ------ | ------------- | ------- | ------------- | ------------- | ------------- |
| Principal    | Sim   | Sim    | Sim           | Sim     | Sim           | Sim           | Sim           |
| Operacional  | Sim   | Sim    | Sim, limitado | Não     | Sim           | Não           | Não           |
| Compras      | Sim   | Não    | Não           | Sim     | Sim, consulta | Sim, consulta | Sim, consulta |
| Planejamento | Sim   | Não    | Não           | Não     | Sim           | Sim, consulta | Sim, consulta |
| Financeiro   | Sim   | Não    | Não           | Não     | Não           | Sim           | Sim           |
| Executivo    | Sim   | Não    | Não           | Não     | Não           | Sim, consulta | Sim           |
| SICK         | Sim   | Sim    | Sim, limitado | Não     | Sim, consulta | Não           | Não           |
| TAGs         | Sim   | Sim    | Sim, limitado | Sim     | Sim           | Sim           | Sim           |

---

# 7. Internacionalização

## Idiomas

O sistema deve suportar:

* português;
* espanhol.

## Regra

O idioma pode ser definido por usuário futuramente.

Usuários em espanhol devem visualizar menus, mensagens, formulários e dashboards traduzidos.

---

# 8. Regras de Segurança

## Interface não é segurança

Ocultar botão não basta.

Toda ação deve validar permissão no backend.

---

## Services devem receber usuário

Services críticos devem receber o usuário responsável pela ação.

Isso permite:

* validar permissão;
* registrar histórico;
* gerar auditoria.

---

## Dados financeiros

Dados financeiros exigem controle especial.

Operadores não devem visualizar valores financeiros, salvo permissão específica.

---

## Exclusões

Exclusões físicas devem ser evitadas.

Preferir:

* inativar;
* baixar;
* cancelar;
* finalizar;
* arquivar.

---

# 9. Permissões Django Planejadas

Permissões importantes do módulo insumos:

```text
aprovar_solicitacao
reprovar_solicitacao
colocar_em_compra
finalizar_solicitacao
realizar_entrada
realizar_saida
realizar_devolucao
realizar_perda
realizar_ajuste
gerenciar_inventarios
gerenciar_checklists
finalizar_checklists
visualizar_custos
visualizar_dashboards_financeiros
gerenciar_tags
```

---

# 10. Grupos Planejados

Grupos funcionais:

```text
INSUMOS_SOLICITANTE
INSUMOS_COMPRAS
INSUMOS_PLANEJAMENTO
INSUMOS_FINANCEIRO
INSUMOS_EXECUTIVO
```

Outros grupos podem ser criados conforme evolução.

---

# 11. Melhorias Futuras

* permissões por grupo de bases;
* perfis compostos;
* idioma por usuário;
* dashboard personalizado por perfil;
* trilha de auditoria avançada;
* aprovação em múltiplos níveis;
* delegação temporária de permissão;
* permissões por ação crítica;
* bloqueio por horário ou operação.

---

# Conclusão

O sistema de permissões deve proteger a operação sem tornar o uso complexo.

A regra principal é:

```text
Usuário certo
↓
Acesso certo
↓
Base certa
↓
Ação certa
↓
Auditoria registrada
```

Permissões bem definidas garantem segurança, rastreabilidade e confiança nos dados do Gerenciador de Estoque.
