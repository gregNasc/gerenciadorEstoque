# Fechamento local K.3–K.5 — Comunicação externa

**Data:** 04/11/2026
**Branch:** `main`
**Status:** implementação local aprovada; ativação externa pendente de configuração
controlada no ambiente.

## K.3 — E-mail SMTP

- adaptador `DjangoEmailProvider` implementado;
- flag própria `NOTIFICACOES_EMAIL_ENABLED`, desligada por padrão;
- criação auditável da entrega por usuário;
- validação de endereço na criação e novamente no processamento;
- payload textual mínimo, sem anexos;
- retry, timeout de processamento e idempotência por entrega;
- teste garante que `--canal EMAIL` nunca usa o provedor Meta.

## K.4 — WhatsApp Meta

- implementação Meta existente preservada;
- consentimento revalidado no processamento;
- revogação cancela entregas pendentes;
- webhook exige assinatura HMAC;
- eventos repetidos ou atrasados não regridem `ENTREGUE`/`LIDA`;
- timeout após possível aceite é marcado para reconciliação, sem retry cego;
- flags permanecem desligadas até credenciais, templates e número serem
  homologados no Render/Meta.

## K.5 — Operação e regressão

- comando `processar_entregas_comunicados` aceita `TODOS`, `EMAIL` e
  `WHATSAPP`;
- comando `diagnosticar_comunicacoes` informa prontidão e filas sem revelar
  credenciais;
- comando `executar_worker_comunicacoes` mantém a fila ativa fora do Web
  Service e pode ser usado diretamente em um Background Worker do Render;
- comando de reenvio permite selecionar o canal;
- nenhuma chamada externa ocorre durante renderização;
- falha de um destinatário não interrompe os demais;
- a aplicação continua funcionando com SMTP/Meta indisponíveis;
- instruções de ativação, pós-deploy e rollback documentadas em
  `docs/release_gate_k_comunicacoes.md`.

## Segurança

- empresa/escopo de integração declarado por entrega;
- usuário e destino revalidados imediatamente antes do envio;
- conteúdo marcado como financeiro exige permissão financeira;
- `jose.barboza` permanece bloqueado para conteúdo financeiro em qualquer
  canal externo;
- erros persistidos não incluem endereço do destinatário nem credenciais.

## Migrations

Nenhuma.

## Testes

- contrato K.1/K.2, e-mail e WhatsApp: **22 aprovados**;
- regressão integrada final com Custódia e Auditoria: **42 aprovados**;
- inclui SMTP em memória, retry, provedor correto, consentimento, revogação,
  webhook assinado, evento fora de ordem, isolamento financeiro e check de
  configuração incompleta.

## Limite externo

O código está pronto para uso, mas a comprovação de entrega real depende de:

- credenciais SMTP válidas;
- conta/número Meta configurado;
- templates aprovados pela Meta;
- webhook público configurado;
- ativação explícita das flags no Render.

Essas ações não foram executadas localmente e não devem ser simuladas como
homologação de produção.
