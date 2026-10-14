# R2.I — Termo de Entrega

## Escopo implementado

- geração automática em PDF a partir da Custódia ativada;
- suporte a múltiplos equipamentos e linhas móveis;
- identificação de colaborador, empresa, Base, data e número da Custódia;
- patrimônio, série, modelo, IMEI, telefone, operadora e ICCID conforme aplicável;
- condição registrada na entrega;
- snapshot imutável dos dados usados no documento;
- armazenamento no backend privado configurado pelo projeto;
- hash SHA-256 do PDF persistido;
- geração idempotente: uma Custódia possui um único Termo de Entrega;
- nenhuma exposição de PIN, PUK ou credenciais móveis.
- layout institucional alinhado ao modelo de referência fornecido, com declaração,
  condições de uso, previsão de devolução, aceite, testemunha do Departamento
  Pessoal e controle interno;
- identificação no formato `CUS-AAAA-NNNN` e responsável real pelo registro.

## Regras

O termo só pode ser emitido para Custódia `ATIVA`, `EM_DEVOLUCAO` ou
`FINALIZADA`, desde que possua ao menos um item. Custódias em rascunho ou
canceladas são rejeitadas.

O PDF e seu snapshot não podem ser alterados depois da geração. Mudanças
posteriores no nome do colaborador, produto ou ativo não reescrevem o documento
histórico.

O bloco de devolução presente no Termo de Entrega é apenas uma previsão em
branco. A devolução efetiva permanece registrada no sistema e produzirá um
documento histórico separado na R2.J, sem sobrescrever este termo.

## Fora do escopo

- tela e endpoint de download;
- Termo de Devolução (R2.J);
- assinatura eletrônica e DocuSign (R2.K);
- testemunha de RH.

## Validação

- 6/6 testes específicos do Termo de Entrega aprovados;
- 96/96 testes de regressão R2.A–R2.I e dependências aprovados;
- migration 0069 aplicada com sucesso no banco de teste;
- `makemigrations --check --dry-run`: nenhuma alteração pendente;
- PDF A4 de duas páginas renderizado e inspecionado visualmente;
- cabeçalhos repetidos, assinaturas, quebras e margens sem defeitos visuais;
- conteúdo extraído e conferido com `pypdf`;
- `manage.py check`: nenhuma inconsistência.

No ambiente isolado, o aplicativo `daphne` foi removido apenas da lista de apps
do processo de teste porque o sandbox bloqueia seu socket interno do `asyncio`.
As configurações persistentes não foram modificadas.
