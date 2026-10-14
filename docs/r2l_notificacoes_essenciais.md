# R2.L — Notificações essenciais da Custódia

## Escopo implementado

Os eventos oficiais abaixo passam a ser registrados pelo Gerenciador:

```text
CUSTODIA_CRIADA
TERMO_GERADO
TERMO_ENVIADO
TERMO_ASSINADO
TERMO_CONCLUIDO
DEVOLUCAO_REGISTRADA
```

`CUSTODIA_CRIADA` é emitido quando a Custódia entra no estado `ATIVA`, não na
gravação de um rascunho.

Cada evento possui chave idempotente, empresa, Custódia, relacionamentos do
domínio, título, mensagem, dados mínimos, usuário responsável e data/hora.
Eventos persistidos são imutáveis.

## Canais

### Sistema

Quando o colaborador possui um `User` ativo vinculado, o serviço cria um
`Comunicado` tenant-aware e uma entrega interna imediatamente marcada como
entregue. O comunicado aparece na infraestrutura já utilizada pelo sistema.

Colaboradores sem `User` continuam participando normalmente do domínio. Nesse
caso não há destinatário interno, mas o evento oficial e os canais externos
aplicáveis continuam registrados.

### E-mail

- utiliza o backend de e-mail configurável do Django;
- não depende de Proton Mail;
- prioriza o e-mail corporativo do `Colaborador`;
- inclui o e-mail configurado para o RH nos eventos DocuSign relevantes;
- permanece desabilitado por padrão;
- envio e retentativas são feitos por outbox.

### WhatsApp

- reutiliza o provedor e os templates já existentes;
- somente cria entrega quando existe `User`, número válido e consentimento ativo;
- respeita revogação do consentimento;
- declara explicitamente o escopo da empresa na integração;
- permanece um canal auxiliar e nunca representa assinatura ou aceite.

## Fonte oficial

O estado da Custódia, dos termos e do envelope DocuSign permanece no banco do
Gerenciador. Falha, atraso, entrega ou leitura em canal externo não altera o
estado oficial desses objetos.

## Auditoria das entregas

Cada entrega registra:

- evento e destinatário;
- canal e provedor;
- status;
- chave idempotente;
- tentativas;
- data de criação, processamento, envio e entrega;
- próxima tentativa;
- erro seguro e resposta sanitizada do provedor.

## Configuração

```text
CUSTODIA_EMAIL_ENABLED=False
CUSTODIA_NOTIFICATION_MAX_RETRIES=5
CUSTODIA_NOTIFICATION_RETRY_BASE_SECONDS=60
CUSTODIA_NOTIFICATION_PROCESSING_TIMEOUT_SECONDS=900
```

O e-mail utiliza também `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`,
`EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` e
`DEFAULT_FROM_EMAIL`.

O WhatsApp continua utilizando as variáveis `WHATSAPP_*` existentes.

## Processamento da outbox

```powershell
python manage.py processar_notificacoes_custodia
python manage.py processar_notificacoes_custodia --canal EMAIL
python manage.py processar_notificacoes_custodia --canal WHATSAPP
```

O comando deve ser executado periodicamente pelo scheduler do ambiente após o
deploy autorizado. Execuções concorrentes usam bloqueio de registros e chaves
idempotentes.

## Segurança

- nenhum PIN, PUK ou segredo é incluído nos eventos;
- credenciais dos provedores permanecem somente em variáveis de ambiente;
- entregas externas são assíncronas e não bloqueiam a operação principal;
- falhas armazenam mensagens seguras, sem exceção ou credencial bruta;
- destinatários e eventos permanecem isolados pela empresa da Custódia;
- WhatsApp exige consentimento explícito.

## Ativação externa pendente

Antes de habilitar os canais em produção:

1. confirmar o provedor SMTP aprovado e configurar os secrets;
2. validar remetente, SPF, DKIM e DMARC quando aplicável;
3. aprovar na Meta os seis templates `custodia_*`;
4. validar os consentimentos e números dos usuários;
5. configurar a execução periódica do comando de outbox;
6. executar envios controlados em homologação;
7. conferir os registros de status, tentativas e erros.

Nenhum e-mail ou WhatsApp real foi enviado durante a implementação.

## Validação local

- 10/10 testes específicos das notificações essenciais aprovados;
- 124/124 testes da regressão R2.A–R2.L aprovados;
- migration aditiva `estoque.0071` aplicada com sucesso no banco de teste;
- `makemigrations --check --dry-run` sem alterações pendentes;
- `manage.py check` sem problemas identificados;
- serviços, comando, testes e migration compilados sem erro de sintaxe.

## Fora do escopo

- uso de WhatsApp como aceite ou assinatura;
- contratação/configuração de provedor SMTP ou Meta;
- tela exclusiva de acompanhamento da outbox;
- deploy, scheduler ou ativação dos canais em produção;
- implementação de EPI/R3.
