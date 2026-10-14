# R2.K — Integração DocuSign

## Escopo implementado

- configuração DocuSign independente por empresa;
- testemunha fixa no papel `SETOR DE RH`, com nome e e-mail configuráveis por tenant;
- envelope vinculado a um único Termo de Entrega ou Termo de Devolução;
- cliente eSignature REST API v2.1 com autenticação OAuth JWT;
- geração do payload na camada `integracao/mappers`, sem chamadas externas nas views de Custódia;
- colaborador como primeiro signatário e RH como testemunha em segundo nível;
- idempotência de envio por termo e versão;
- persistência do `envelope_id`, participantes, estados e datas relevantes;
- webhook JSON SIM com validação HMAC sobre o corpo bruto;
- aceitação de cabeçalhos numerados para rotação de chave HMAC;
- eventos imutáveis e idempotentes;
- proteção contra regressão de estado causada por evento atrasado;
- download do PDF combinado concluído e do certificado de conclusão;
- arquivos concluídos em armazenamento privado por empresa, com hash SHA-256;
- payload de evento sanitizado antes da persistência.

## Configuração por empresa

O model `DocusignTenantConfig` controla:

- habilitação explícita;
- ID opcional da conta DocuSign;
- nome da testemunha de RH;
- e-mail da testemunha de RH.

Uma empresa não utiliza a configuração de outra. A configuração só pode ser
habilitada quando o e-mail do RH estiver preenchido.

## Secrets e ambiente

Nenhuma credencial é persistida no banco. A ativação exige:

```text
DOCUSIGN_ENABLED=True
DOCUSIGN_AUTH_SERVER=https://account-d.docusign.com
DOCUSIGN_ESIGN_BASE_URL=https://demo.docusign.net/restapi
DOCUSIGN_INTEGRATION_KEY=...
DOCUSIGN_USER_ID=...
DOCUSIGN_PRIVATE_KEY=...
DOCUSIGN_ACCOUNT_ID=...
DOCUSIGN_WEBHOOK_HMAC_SECRET=...
DOCUSIGN_TIMEOUT=20
DOCUSIGN_MAX_RETRIES=3
DOCUSIGN_BACKOFF_BASE=1
APP_BASE_URL=https://endereco-publico-da-aplicacao
```

Em produção, os hosts de autenticação e eSignature devem ser substituídos pelos
valores entregues pela conta DocuSign após homologação. `APP_BASE_URL` precisa
usar HTTPS.

## Estados persistidos

```text
PREPARANDO
ENVIADO
ENTREGUE
ASSINADO
CONCLUIDO
RECUSADO
ANULADO
ERRO
```

Estados terminais não retrocedem quando um webhook antigo chega depois.

## Segurança

- integração desabilitada por padrão;
- falha fechada quando secrets, conta, e-mail do colaborador ou RH estiverem ausentes;
- JWT assinado com RSA, sem registrar chave privada ou token;
- URLs externas obrigatoriamente HTTPS;
- webhook limitado a 1 MB e validado antes de interpretar JSON;
- status do frontend não é utilizado como fonte de verdade;
- PDFs e certificados não são aceitos do payload do webhook: são baixados pela API;
- dados PDF/base64, tokens, passwords e secrets são removidos dos eventos persistidos;
- isolamento de empresa validado pelo model do envelope.

## Validação externa pendente

O fluxo foi implementado e testado com cliente HTTP simulado. Ainda é necessário,
antes de ativar em produção:

1. confirmar que o plano DocuSign contratado permite eSignature API;
2. criar uma aplicação Developer/homologação;
3. conceder consentimento ao usuário de integração para o fluxo JWT;
4. configurar os secrets fora do repositório;
5. cadastrar/confirmar a chave HMAC do Connect;
6. enviar um envelope real de homologação;
7. validar assinatura do colaborador, testemunha do RH, webhook e arquivamento;
8. somente então trocar para os endpoints e a conta de produção.

Não houve tentativa de acesso à API real sem credenciais e autorização.

## Validação local

- 12/12 testes específicos da integração DocuSign aprovados;
- 114/114 testes da regressão R2.A–R2.K aprovados;
- migration `integracao.0005` aplicada com sucesso no banco de teste;
- `makemigrations --check --dry-run` sem alterações pendentes;
- `manage.py check` sem problemas identificados;
- módulos novos compilados sem erro de sintaxe.

## Fora do escopo

- tela operacional para disparo manual do envelope;
- página de acompanhamento de assinaturas;
- configuração DocuSign disponível diretamente no painel do tenant;
- ativação de conta ou contratação de plano DocuSign;
- notificações internas/e-mail/WhatsApp da R2.L.
