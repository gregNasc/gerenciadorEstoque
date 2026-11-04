# Relatório R7.C.2 — Cotações persistentes por solicitação

## Objetivo

Criar um processo de cotação auditável, ligado à Solicitação de Insumos do R6,
sem selecionar automaticamente o menor preço e sem expor valores a perfis sem
permissão financeira.

## Entregas

- Um único processo de cotação por solicitação, sempre vinculado à empresa da Base.
- Registro de propostas de múltiplos fornecedores homologados e ativos.
- Valores por item, quantidade, CA opcional, frete, impostos, desconto, prazo,
  validade e condição de pagamento.
- Comparação visual com destaque informativo para o menor valor.
- Decisão exclusivamente humana, com justificativa obrigatória e identificação
  do usuário e horário da decisão.
- Histórico não financeiro na linha do tempo da solicitação: abertura, proposta
  recebida e decisão registrada.
- Link de acesso dentro da solicitação apenas para Compras/Admin autorizado.
- Isolamento por tenant e Base, inclusive nas leituras e gravações do serviço.
- Bloqueio explícito para Gestor, Operador sem perfil Compras e `jose.barboza`.

## Segurança e regras

- Fornecedor pendente, suspenso, inativo ou pertencente a outro tenant não pode
  receber proposta.
- Um item de outra solicitação invalida e reverte a proposta completa.
- O sistema não escolhe automaticamente a proposta de menor valor.
- É permitido escolher outra proposta quando a justificativa humana documenta a
  decisão.
- Os eventos visíveis ao solicitante não armazenam preços ou condições financeiras.
- Esta subetapa não cria Aquisição automaticamente; essa integração permanece
  separada para evitar efeitos financeiros implícitos.

## Banco de dados

- `compras.0006_cotacaofornecedor_processocotacao_and_more`
- `insumos.0052_alter_eventosolicitacaoinsumo_tipo`

As migrações são aditivas: criam tabelas, relacionamentos, índices e tipos de
evento. Não removem nem reescrevem solicitações, fornecedores ou aquisições
existentes.

## Validação executada

- `manage.py check`: sem problemas.
- `makemigrations --check --dry-run`: nenhuma alteração pendente.
- Testes específicos R7.C.2: 7/7 aprovados.
- Suíte completa de Compras: 55/55 aprovados.
- Testes integrados de solicitações, eventos, perfil Compras e preços: 28/28
  aprovados.
- Badge R6/K.1: 5/5 aprovados.

Total consolidado: **88 testes distintos aprovados** (95 execuções aprovadas,
contando a repetição da suíte específica após o ajuste de integração).

## Estado da entrega

R7.C.2 concluída localmente. Nenhum commit, push, deploy ou migração no banco
operacional foi executado nesta subetapa.
