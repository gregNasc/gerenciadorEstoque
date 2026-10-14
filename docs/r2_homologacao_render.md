# R2 — Runbook de homologação no Render

Este procedimento prepara a R2 sem ativar DocuSign, e-mail ou WhatsApp no
primeiro deploy. A `SECRET_KEY` atual deve ser preservada.

## 1. Pré-requisitos obrigatórios

- backup verificável do PostgreSQL antes das migrations;
- Redis acessível em `CHANNEL_REDIS_URL`;
- disco persistente montado e `PERSISTENT_STORAGE_ROOT=/var/data`, ou S3
  configurado;
- `DATABASE_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` e `APP_BASE_URL`
  apontando para o ambiente correto;
- `LINHAS_MOVEIS_CREDENTIAL_KEYS` preservada, sem reutilizar a `SECRET_KEY`;
- `DOCUSIGN_ENABLED=False`, `CUSTODIA_EMAIL_ENABLED=False` e
  `WHATSAPP_ENABLED=False`.

## 2. Validação antes de publicar

```powershell
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
```

Durante a homologação inicial, `SECURE_HSTS_PRELOAD=False` é intencional. O
aviso `security.W021` pode permanecer até a validação definitiva do domínio.

## 3. Primeiro deploy

```powershell
python manage.py migrate --noinput
python manage.py collectstatic --noinput
```

Depois do deploy, confirmar:

- migrations `estoque.0063` a `estoque.0071` e `integracao.0005` aplicadas;
- login e navegação de Superuser, Admin, Gestor e Operador;
- isolamento entre empresas e bases;
- criação de Colaborador sem conta de acesso;
- Custódia com equipamento e chip elegíveis;
- geração e leitura protegida dos Termos de Entrega e Devolução;
- persistência dos arquivos após reiniciar o serviço;
- WebSocket/Redis e fluxo normal de chamados.

## 4. Ativação gradual

1. Configurar DocuSign de demonstração e habilitar somente um tenant de
   homologação.
2. Validar um envelope completo: colaborador, RH, webhook, PDF e certificado.
3. Homologar SMTP e então habilitar `CUSTODIA_EMAIL_ENABLED`.
4. Aprovar templates e consentimentos antes de habilitar WhatsApp.
5. Configurar o scheduler de `processar_notificacoes_custodia` somente depois
   da homologação dos canais.

## 5. Contenção e rollback

- desabilitar imediatamente as três integrações externas;
- interromper o scheduler da outbox;
- reverter a aplicação sem apagar tabelas, termos, envelopes ou eventos;
- restaurar banco e arquivos apenas em caso de corrupção confirmada;
- qualquer rollback de schema exige cópia recente do PostgreSQL e autorização
  separada.
