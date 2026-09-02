# Uploads persistentes

Imagens e arquivos enviados pelo sistema não devem ficar no diretório do
deploy. Em produção, o projeto recusa a inicialização quando nenhum storage
persistente está configurado.

## Opção 1: disco persistente no Render

1. No serviço web, adicione um Persistent Disk montado em `/var/data`.
2. Defina a variável `PERSISTENT_STORAGE_ROOT=/var/data`.
3. Mantenha `USE_S3=False`.
4. Faça um novo deploy.

O Django passa a gravar arquivos públicos em `/var/data/media` e privados em
`/var/data/private_media`. O mesmo disco precisa permanecer anexado ao serviço
em todos os deploys. Antes do primeiro deploy com essa configuração, copie para
essas pastas os arquivos que ainda existirem no filesystem antigo; registros do
banco guardam apenas o nome do arquivo e não recuperam um binário já perdido.

O Render disponibiliza Persistent Disk somente em serviços pagos. Um serviço
com disco fica limitado a uma instância e os deploys têm uma breve interrupção;
se o serviço precisar de múltiplas instâncias ou zero downtime, use S3.

## Opção 2: S3 ou storage compatível

Defina no serviço:

```text
USE_S3=True
AWS_STORAGE_BUCKET_NAME=nome-do-bucket
AWS_S3_REGION_NAME=sa-east-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

Para um serviço compatível com S3, informe também `AWS_S3_ENDPOINT_URL`. O
bucket deve ser privado; downloads protegidos usam URLs assinadas. Novos
arquivos públicos ficam sob `media/` e documentos privados sob `private/`.

## Verificação rápida

Depois do deploy, envie uma imagem e um anexo, anote os respectivos nomes,
execute outro deploy e confirme que ambos continuam abrindo. Não remova o disco
nem troque de bucket sem antes migrar os objetos.
