# Release Gate K — E-mail e WhatsApp

## Estado

Implementação local pronta para implantação controlada. Os canais permanecem
desligados por padrão e não há migration nova.

## O que foi concluído

- fila única e auditável em `ComunicadoEntrega`;
- roteamento independente para `EMAIL` e `WHATSAPP`;
- e-mail pelo backend SMTP nativo do Django;
- WhatsApp pelo provedor Meta já existente;
- processamento fora da requisição HTTP;
- recuperação de entregas travadas;
- retry exponencial configurável por canal;
- idempotency key enviada ao backend de e-mail e ao provedor Meta;
- revalidação de e-mail, usuário ativo e consentimento WhatsApp no processamento;
- cancelamento das pendências quando o consentimento é revogado;
- webhook Meta assinado, idempotente e sem regressão de status;
- timeout ambíguo do Meta não é reenviado automaticamente, evitando
  duplicidade após possível aceite pelo provedor;
- bloqueio de conteúdo marcado como financeiro para destinatários sem permissão,
  inclusive `jose.barboza`;
- nenhum anexo é enviado automaticamente pelos canais externos;
- um único comando operacional processa os dois canais.

## Variáveis do Render — e-mail

```dotenv
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.seu-provedor.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL=
NOTIFICACOES_EMAIL_ENABLED=False
NOTIFICACOES_EMAIL_MAX_RETRIES=5
NOTIFICACOES_EMAIL_RETRY_BASE_SECONDS=60
NOTIFICACOES_EMAIL_PROCESSING_TIMEOUT_SECONDS=900
```

Após validar SMTP com uma conta autorizada, alterar apenas:

```dotenv
NOTIFICACOES_EMAIL_ENABLED=True
```

## Variáveis do Render — WhatsApp Meta

```dotenv
WHATSAPP_ENABLED=False
WHATSAPP_PROVIDER=disabled
WHATSAPP_API_BASE_URL=https://graph.facebook.com
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_BUSINESS_ACCOUNT_ID=
WHATSAPP_WEBHOOK_VERIFY_TOKEN=
WHATSAPP_WEBHOOK_APP_SECRET=
WHATSAPP_DEFAULT_COUNTRY_CODE=55
WHATSAPP_TIMEOUT=10
WHATSAPP_MAX_RETRIES=5
WHATSAPP_RETRY_BASE_SECONDS=60
WHATSAPP_PROCESSING_TIMEOUT_SECONDS=900
```

Depois de configurar número, token, templates aprovados e webhook, habilitar:

```dotenv
WHATSAPP_PROVIDER=meta
WHATSAPP_ENABLED=True
```

Webhook público:

```text
https://gerenciadorestoque.onrender.com/integracoes/whatsapp/webhook/
```

## Processamento operacional

Antes de habilitar qualquer canal, conferir a prontidão sem expor segredos:

```bash
python manage.py diagnosticar_comunicacoes
python manage.py diagnosticar_comunicacoes --json
```

No Render, criar um **Background Worker** usando o mesmo repositório e as
mesmas variáveis do Web Service.

Start Command recomendado:

```bash
python manage.py executar_worker_comunicacoes --intervalo 15 --limit 100
```

Como alternativa, executar fora do processo web de forma recorrente:

```bash
python manage.py processar_entregas_comunicados --canal TODOS --limit 100
```

Para isolar um canal durante diagnóstico:

```bash
python manage.py processar_entregas_comunicados --canal EMAIL --limit 100
python manage.py processar_entregas_comunicados --canal WHATSAPP --limit 100
```

Não acrescentar o worker ao comando do Web Service. O processo de comunicação
deve poder reiniciar ou ser pausado sem interromper o sistema principal.

Falhas definitivas somente devem ser reabertas após correção da causa:

```bash
python manage.py reenviar_entregas_falhas --canal EMAIL --limit 100
python manage.py reenviar_entregas_falhas --canal WHATSAPP --limit 100
```

## Ativação progressiva

1. publicar o código com as duas flags desligadas;
2. executar `migrate` normalmente (não há migration nova desta etapa);
3. criar o Background Worker ainda com as flags desligadas;
4. executar `diagnosticar_comunicacoes` no Shell do Render;
5. configurar SMTP e testar um destinatário autorizado;
6. habilitar e-mail e observar fila, falhas e duplicidades;
7. configurar Meta, consentimento e templates aprovados;
8. validar o webhook assinado;
9. habilitar WhatsApp para destinatários de teste;
10. expandir somente após confirmar status e ausência de vazamento de dados.

## Templates que devem existir na Meta

Os nomes abaixo precisam ser aprovados com dois parâmetros no corpo
(`titulo`, `mensagem`) e um botão de URL dinâmica:

```text
auditoria_aberta
auditoria_proxima_vencimento
auditoria_enviada
auditoria_resultado_final
auditoria_correcao_solicitada
auditoria_divergencia
auditoria_equipamento_mantido
auditoria_transferencia_criada
auditoria_campanha_acao
transferencia_enviada
transferencia_recebida
emprestimo_enviado
emprestimo_recebido
comunicado_urgente
chamado_acao
custodia_criada
custodia_termo_gerado
custodia_termo_enviado
custodia_termo_assinado
custodia_termo_concluido
custodia_devolucao_registrada
```

## Rollback

Desabilitar imediatamente os canais sem apagar histórico:

```dotenv
NOTIFICACOES_EMAIL_ENABLED=False
WHATSAPP_ENABLED=False
WHATSAPP_PROVIDER=disabled
```

Interromper o agendamento do comando se necessário. As entregas e tentativas
permanecem auditáveis no banco para diagnóstico e reconciliação.

## Validação pós-deploy

- comunicado interno continua aparecendo com canais externos desligados;
- e-mail chega apenas ao endereço atual do usuário;
- usuário inativo ou e-mail alterado não recebe entrega antiga;
- WhatsApp sem consentimento ou revogado não é enviado;
- callback `sent → delivered → read` avança sem regressão;
- callback repetido não duplica entrega;
- falha de SMTP ou Meta não interrompe Solicitações ou Compras;
- `jose.barboza` não recebe conteúdo financeiro;
- escopo de empresa e Base permanece protegido no link de destino.
