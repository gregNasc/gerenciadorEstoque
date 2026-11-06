# Configuração de e-mail no Render

Este guia prepara o endereço remetente e explica de onde vêm os destinatários. Nunca envie a senha do e-mail pelo chat nem a grave no repositório.

## 1. Obtenha os dados SMTP

Solicite ao responsável pelo e-mail corporativo:

- servidor SMTP;
- porta (normalmente 587 com TLS, mas confirme com o provedor);
- endereço que enviará as mensagens;
- senha de aplicativo ou token SMTP;
- confirmação de que o envio SMTP está liberado para essa conta.

Senhas comuns da caixa postal podem ser recusadas quando a conta usa autenticação em dois fatores. Nesse caso, use a senha de aplicativo ou o método indicado pelo provedor.

No Gmail, ative a verificação em duas etapas e gere uma senha de app. O código
gerado tem 16 dígitos; grave-o em `EMAIL_HOST_PASSWORD` sem espaços. A senha
comum da conta não deve ser usada para SMTP.

## 2. Cadastre as variáveis no Render

No serviço web, abra **Environment** e configure:

```text
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=servidor informado pelo provedor
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_TIMEOUT=30
EMAIL_HOST_USER=email remetente
EMAIL_HOST_PASSWORD=senha de aplicativo ou token SMTP
DEFAULT_FROM_EMAIL=email remetente
NOTIFICACOES_EMAIL_ENABLED=False
CUSTODIA_EMAIL_ENABLED=False
```

Mantenha os dois canais desativados até concluir o teste. Se o provedor exigir porta ou segurança diferentes, use exatamente os valores fornecidos por ele.

## 3. Valide sem enviar

No Shell do Render:

```powershell
python manage.py testar_email_smtp --destino destinatario@empresa.com
```

O comando valida o preenchimento e mascara o endereço na saída. Ele não mostra credenciais e não envia mensagem sem confirmação.

## 4. Envie somente um teste controlado

```powershell
python manage.py testar_email_smtp --destino destinatario@empresa.com --enviar
```

Confirme a chegada na caixa de entrada e no spam. Se falhar, mantenha os canais desativados e confira host, porta, TLS, usuário, token e a liberação SMTP da conta.

## 5. Defina quem recebe

Não existe uma lista global oculta de destinatários. Cada endereço tem uma origem auditável:

- **Comunicados do sistema:** usam o campo **E-mail** do cadastro do usuário ativo, respeitando empresa, Base, perfil e assunto autorizado.
- **Custódia do colaborador:** usa o e-mail do cadastro do colaborador vinculado à Custódia.
- **Eventos de assinatura destinados ao RH:** usam o campo de e-mail da testemunha/RH na configuração de assinatura eletrônica da empresa.

Portanto, os e-mails que receberão mensagens devem ser preenchidos nos cadastros correspondentes. O usuário `jose.barboza` é excluído de comunicações de Planejamento de Consumo, identificação de recebimento, Custódia, preços, cotações e valores financeiros, inclusive quando houver uma entrega antiga aguardando processamento.

## 6. Ative gradualmente

Depois do teste SMTP bem-sucedido:

1. altere `NOTIFICACOES_EMAIL_ENABLED=True`;
2. faça o deploy/restart;
3. execute `python manage.py diagnosticar_comunicacoes`;
4. mantenha o worker de comunicados ativo:

```powershell
python manage.py executar_worker_comunicacoes --intervalo 15 --limit 100
```

Ative `CUSTODIA_EMAIL_ENABLED=True` somente quando também quiser enviar e-mails de Custódia e houver um processo separado executando:

```powershell
python manage.py processar_notificacoes_custodia --canal EMAIL --limit 100
```

## 7. Interrupção segura

Para interromper novos envios sem apagar o histórico, defina novamente:

```text
NOTIFICACOES_EMAIL_ENABLED=False
CUSTODIA_EMAIL_ENABLED=False
```

Depois faça restart/deploy do serviço. O histórico auditável permanece preservado.
