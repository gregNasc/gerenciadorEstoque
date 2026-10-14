# R2.J — Termo de Devolução

## Escopo implementado

- geração automática ao registrar cada ocorrência de devolução;
- documento próprio, separado do Termo de Entrega;
- suporte a devolução total e parcial;
- um termo por ocorrência, inclusive para retorno posterior de item faltante;
- situação, condição e observação individual de cada item;
- motivo, observações gerais e responsável pelo recebimento;
- snapshot imutável e armazenamento privado;
- hash SHA-256 do PDF persistido;
- geração idempotente e sem exposição de credenciais móveis;
- identidade visual alinhada ao Termo de Entrega aprovado.

## Preservação histórica

O Termo de Devolução referencia a ocorrência de devolução, não substitui nem
altera o Termo de Entrega. Em uma devolução parcial, o primeiro termo registra
os itens devolvidos e faltantes; uma ocorrência posterior gera outro termo para
os itens então devolvidos.

## Fora do escopo

- telas e endpoints de impressão/download;
- assinatura eletrônica e DocuSign (R2.K);
- webhook e armazenamento do PDF assinado.

## Validação

- 6/6 testes específicos do Termo de Devolução aprovados;
- 102/102 testes da regressão R2.A–R2.J aprovados;
- migration 0070 aplicada com sucesso no banco de teste;
- `makemigrations --check --dry-run` sem alterações pendentes;
- `manage.py check` sem problemas identificados;
- amostra A4 com itens devolvidos e faltantes renderizada e inspecionada;
- tabela, resumo, assinaturas, testemunha e controle interno sem cortes;
- credenciais móveis ausentes do snapshot e do PDF.
