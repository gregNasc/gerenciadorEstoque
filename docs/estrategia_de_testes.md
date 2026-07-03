# 12 — Estratégia de Testes

## Objetivo

Este documento define a estratégia de qualidade do Gerenciador de Estoque.

Seu objetivo é garantir que novas funcionalidades, correções e refatorações possam ser realizadas com segurança, preservando o funcionamento do sistema.

Os testes devem validar não apenas o código, mas principalmente as regras de negócio.

---

# 1. Filosofia

O objetivo dos testes não é provar que o código funciona.

O objetivo é garantir que a operação continue funcionando.

A pergunta principal deve ser:

> "Se alterarmos este módulo hoje, existe alguma regra da operação que poderá ser quebrada?"

Se a resposta for "sim", essa regra precisa estar protegida por testes.

---

# 2. Pirâmide de Testes

```text
                 Testes Manuais
                      ▲
               Testes de Integração
                      ▲
              Testes Unitários (Services)
```

A maior parte dos testes deverá estar concentrada nos Services.

---

# 3. Ordem de Prioridade

Os testes deverão ser implementados na seguinte ordem:

1. Services;
2. Regras de negócio;
3. APIs;
4. Views;
5. Templates (quando necessário).

---

# 4. O que deve ser testado

## Estoque

* cadastro de equipamentos;
* alteração de status;
* transferências;
* empréstimos;
* recebimentos;
* devoluções;
* histórico;
* SICK.

---

## Insumos

* entrada;
* saída;
* devolução;
* perda;
* ajuste;
* saldo;
* custo médio;
* estoque mínimo.

---

## Inventários

* criação;
* edição;
* finalização;
* status.

---

## Checklist

* criação;
* equipamentos;
* insumos;
* TAGs;
* validações;
* finalização.

---

## TAGs

* envio;
* retorno;
* perdas;
* cálculo por faixa;
* cálculo de custo.

---

## Custos

* consumo;
* perdas;
* reutilização;
* custo por inventário;
* custo por cliente;
* custo por base;
* custo por grupo.

---

# 5. Testes Unitários

## Objetivo

Validar cada Service isoladamente.

Exemplo:

MovimentacaoService.

Deve garantir:

* entrada aumenta saldo;
* saída reduz saldo;
* saldo negativo não é permitido;
* ajuste gera histórico.

---

Outro exemplo.

ChecklistService.

Deve garantir:

* não finaliza sem retorno;
* não aceita inconsistência;
* gera consumo;
* gera movimentações.

---

# 6. Testes de Integração

Objetivo.

Validar comunicação entre módulos.

Exemplos.

ChecklistService

↓

MovimentacaoService

↓

ConsumoService

↓

DashboardService

Todos devem funcionar juntos.

---

# 7. Testes das APIs

Validar.

Autenticação.

Permissões.

JSON.

Códigos HTTP.

Filtros.

Paginação.

Mensagens de erro.

---

# 8. Testes dos Dashboards

Validar.

KPIs.

Consultas.

Filtros.

Drill-down.

Tempo de resposta.

---

# 9. Testes de Permissão

Cada perfil deve ser validado.

Administrador.

Gestor.

Operador.

Compras.

Planejamento.

Financeiro.

Executivo.

Nenhum usuário deve visualizar informações indevidas.

---

# 10. Testes de Performance

Monitorar.

Consultas.

Tempo de resposta.

Consumo de memória.

Uso do banco.

Dashboards.

---

# 11. Testes de Segurança

Validar.

Autenticação.

Permissões.

CSRF.

SQL Injection.

XSS.

Upload de arquivos.

---

# 12. Testes Manuais

Antes de cada deploy importante.

Checklist.

Cadastro.

Transferências.

Empréstimos.

Inventários.

Checklists.

Dashboards.

Notificações.

---

# 13. Cenários Críticos

Alguns cenários nunca podem deixar de ser testados.

## Equipamentos

Transferir.

Cancelar.

Receber.

Emprestar.

Devolver.

SICK.

---

## Insumos

Entrada.

Saída.

Perda.

Devolução.

Ajuste.

---

## TAGs

Enviar faixa.

Retornar faixa.

Perder faixa.

Calcular custo.

---

## Inventários

Criar.

Editar.

Finalizar.

Reabrir (quando permitido).

---

## Custos

Consumíveis.

Reutilizáveis.

TAGs.

Perdas.

---

# 14. Testes de Regressão

Sempre que um módulo sofrer alteração importante.

Executar novamente.

Equipamentos.

Insumos.

Inventários.

Dashboards.

Permissões.

Integrações.

---

# 15. Cobertura

Não existe meta de cobertura baseada apenas em porcentagem.

A prioridade é cobrir regras críticas da operação.

Uma regra importante protegida vale mais do que dezenas de testes superficiais.

---

# 16. Automação

A longo prazo.

Testes deverão ser executados automaticamente.

Fluxo esperado.

```text
Commit

↓

Testes

↓

Validação

↓

Deploy
```

Deploy não deve ocorrer caso testes críticos falhem.

---

# 17. Critérios para Refatoração

Antes de refatorar um módulo.

1. Documentação atualizada.
2. Testes existentes.
3. Refatoração.
4. Execução dos testes.
5. Revisão.
6. Deploy.

---

# 18. Indicadores de Qualidade

Indicadores futuros.

Quantidade de testes.

Tempo médio de execução.

Falhas.

Cobertura de regras críticas.

Tempo médio para correção.

---

# 19. Roadmap

## Curto Prazo

Testes dos Services.

---

## Médio Prazo

Testes das APIs.

---

## Longo Prazo

Pipeline completo de testes automáticos.

---

# 20. Filosofia Final

O Gerenciador de Estoque representa uma operação real.

Uma alteração aparentemente pequena pode impactar:

* estoque;
* custos;
* inventários;
* dashboards;
* compras;
* planejamento.

Por isso, os testes devem proteger as regras da operação, e não apenas o código.

Cada nova funcionalidade deve nascer acompanhada de testes compatíveis com sua criticidade.

---

# Conclusão

A estratégia de testes do Gerenciador de Estoque tem como objetivo preservar a confiança na evolução do sistema.

O crescimento da plataforma deve acontecer de forma contínua, segura e previsível.

A documentação, os Services e os testes formam a base que permitirá evoluir o sistema durante muitos anos sem comprometer sua estabilidade.
