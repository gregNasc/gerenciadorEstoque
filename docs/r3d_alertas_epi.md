# R3.D — Alertas de EPI

## Estados preparados

O serviço `AlertaEpiService` calcula os estados sem alterar o preenchimento do
Checklist e sem tornar datas obrigatórias.

### Certificado CA

- `CA_VALIDO`
- `CA_PROXIMO`, com faixas de 90, 60 e 30 dias
- `CA_VENCIDO`
- `CA_DIVERGENTE`
- `CA_INEXISTENTE`

### Validade física

- `VALIDADE_FISICA_VALIDA`
- `VALIDADE_FISICA_PROXIMA`, com faixas de 90, 60 e 30 dias
- `EPI_VENCIDO`
- `SEM_VALIDADE_FISICA`

A ausência de validade é aceita e recebe um estado próprio; ela não impede o
cadastro nem é interpretada como vencimento.

## Cadastro operacional

O cadastro e a edição de Insumos agora exibem a seção de EPI quando a natureza
selecionada for `EPI`.

Obrigatórios para EPI:

- Base;
- número do CA;
- tamanho ou variante.

Opcionais:

- fabricante/importador;
- validade do CA;
- número do lote;
- data de fabricação;
- validade física do lote;
- observação.

Mesmo sem número de lote ou datas, o registro de Base é criado para que o EPI
permaneça isolado no tenant correto. Botas podem usar tamanhos como 37, 38, 39
ou 40; outros EPIs podem utilizar uma variante descritiva, como `ÚNICO`.

## Banco de dados

A migration `0042_alter_loteepi_codigo_lote_and_more.py` permite fabricante e
número de lote vazios. Ela não remove nem reclassifica registros existentes.

## Limite

A R3.D prepara os estados e faixas para consumo pelas próximas interfaces. Não
foram criados disparos automáticos de e-mail, WhatsApp ou notificações.

## Validação

- 12 testes direcionados de cadastro, isolamento e alertas aprovados;
- 85 testes da regressão completa de `insumos` aprovados;
- `manage.py check` sem problemas;
- nenhuma alteração de migration pendente;
- catálogo espanhol compilado com sucesso.
