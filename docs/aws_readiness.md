# Preparação do Django para AWS

Este documento cobre somente a preparação do código. Ele não cria recursos AWS,
não altera DNS e não executa migração de dados.

## Arquitetura de referência

```text
Route 53 -> ALB/ACM -> EC2 (Gunicorn/Django) -> RDS PostgreSQL privado
                                      |
                                      +-> S3 privado para mídia
```

Use IAM Role na EC2 para acessar S3 e serviços AWS. Não grave chaves AWS em
arquivos ou variáveis quando a Role puder fornecer credenciais temporárias.

## Configuração mínima de produção

Defina, no Secrets Manager, Parameter Store ou mecanismo equivalente:

```dotenv
DJANGO_ENVIRONMENT=production
DEBUG=False
SECRET_KEY=<segredo-forte>
ALLOWED_HOSTS=estoque.exemplo.com
CSRF_TRUSTED_ORIGINS=https://estoque.exemplo.com
DATABASE_URL=postgresql://usuario:senha@rds-privado:5432/estoque
DATABASE_SSL_REQUIRED=True
USE_S3=True
AWS_STORAGE_BUCKET_NAME=<bucket-privado>
AWS_S3_REGION_NAME=sa-east-1
CSRF_COOKIE_SECURE=True
SESSION_COOKIE_SECURE=True
SECURE_SSL_REDIRECT=True
```

Mantenha `SECURE_HSTS_SECONDS=0` na primeira homologação. Ative HSTS somente
depois de validar domínio, certificado, redirecionamento HTTPS e todos os
subdomínios relevantes.

Instale as dependências do projeto com:

```bash
pip install -r requirements.txt
```

Os arquivos estáticos continuam atendidos pelo WhiteNoise. Arquivos de mídia
usam armazenamento local quando `USE_S3=False` e S3 privado quando
`USE_S3=True`. Downloads de anexos de comunicados passam por uma view
autenticada e autorizada; o bucket não deve permitir acesso público.

## Health checks

- `GET /health/live/`: confirma que o processo Django responde; não consulta o banco.
- `GET /health/ready/`: executa `SELECT 1`; retorna HTTP 503 se o PostgreSQL não estiver disponível.

Configure o target group do ALB para usar `/health/ready/`. Use
`/health/live/` para diagnóstico do processo, não como prova de prontidão.

## Sequência de homologação

1. Criar VPC, sub-redes, Security Groups, ALB/ACM, EC2, RDS e S3 separados da produção.
2. Instalar a aplicação e executar `python manage.py check --deploy`.
3. Restaurar uma cópia autorizada do PostgreSQL e reconciliar contagens.
4. Sincronizar uma cópia autorizada da mídia e validar imagens, PDFs e nomes especiais.
5. Executar migrations, `collectstatic`, health checks e smoke tests.
6. Validar recuperação de senha, anexos protegidos, logs e alertas.
7. Ensaiar backup e restauração e registrar duração, RPO e RTO observados.
8. Só então preparar a janela de corte e o plano de rollback.

## Rollback do código

Reimplante o commit anterior e restaure as variáveis anteriores. Se já houver
novas gravações na AWS, não aponte o DNS de volta para outro banco sem antes
reconciliar os dados. Migrations futuras devem possuir plano próprio de
reversão ou compensação.

## Pendências externas

- conta e região AWS definitivas;
- VPC, sub-redes, nomes e tags corporativas;
- domínio e responsável pelo DNS;
- política de backup, retenção e custos;
- acessos de homologação/produção e pipeline;
- responsáveis pela aprovação da mudança e pelo teste de restauração.
