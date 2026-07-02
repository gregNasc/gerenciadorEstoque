#  Gerenciador de Estoque - Plano Mestre

## Visão Geral

Sistema para controle de equipamentos por regional, com:

* Controle individual por serial/patrimônio
* Transferências entre regionais
* Histórico completo de movimentações
* Permissões por usuário/regional
* Sistema de notificações
* Atualização em tempo Real de Status de transferências
* Caixa de Mensagens 
---

##  Arquitetura Atual

### Principais entidades

* Equipamento
* Transferencia
* ItemTransferencia
* Historico
* Notificacao
* Perfil / Permissões

---

## Problemas Atuais

### Críticos (quebram regra de negócio)

* [ ] Possível inconsistência entre Solicitação x Transferência
* [ ] Notificações sendo criadas de forma duplicada ou errada
* [ ] Marcação de Sick

---

### Médios (funciona, mas errado/instável)

* [ ] Tipos de notificação mal definidos ("Sistema" confuso)
* [ ] Falta de padronização nas mensagens
* [ ] Apresentação dos modais

---

### Melhorias (qualidade/UX)

* [ ] Melhorar tela de transferências
* [ ] Melhorar organização visual do sistema
* [ ] Feedback visual para ações (sucesso/erro)

---

## Regras de Negócio (NÃO PODE QUEBRAR)

* Equipamento:

  * Serial único
  * Patrimônio único

* Transferência:

  * Deve ter protocolo único
  * Pode conter múltiplos itens
  * Só pode ser concluída com confirmação

* Histórico:

  * Toda ação relevante deve ser registrada

* Permissões:

  * Usuário só atua dentro da sua regional
  * Controle de envio/recebimento

---

## Fluxos do Sistema

### Fluxo de Transferência

1. Usuário solicita transferência
2. Sistema cria Transferencia (status: PENDENTE)
3. Sistema gera Notificação para destino
4. Destino visualiza
5. Destino confirma recebimento
6. Sistema:

   * Atualiza estoque
   * Atualiza status
   * Gera histórico

---

### Fluxo de Notificação

1. Evento ocorre (solicitação, transferência, sistema)
2. Notificação é criada
3. Usuário visualiza
4. Usuário marca como lida
5. Badge deve refletir apenas NÃO lidas

---

## Pontos Técnicos a Revisar

* [ ] Query de contagem de notificações (badge)
* [ ] Onde as notificações são criadas (views? signals?)
* [ ] Possível duplicidade de criação
* [ ] Consistência entre models e templates
* [ ] Uso de signals vs lógica explícita

---

## Estratégia de Correção

### Fase 1 (Crítico)

* Corrigir contagem de notificações
* Garantir integridade das notificações

### Fase 2 (Estabilidade)

* Corrigir templates quebrados
* Ajustar tipos de notificação

### Fase 3 (Melhoria)

* UX
* Padronização visual
* Feedbacks

---

## Decisões Técnicas (IMPORTANTE)

* Evitar lógica duplicada (signals + views ao mesmo tempo)
* Preferir clareza > 
* Sempre garantir rastreabilidade no Histórico

---

## Observações

* Sistema já funcional, foco agora é consistência e confiabilidade
* Evitar mudanças grandes sem validar fluxo completo
* Sempre testar fluxo completo de transferência após alterações
