# R7.F — Recebimento inteligente

## Resultado

O recebimento de compras agora compara três referências sem criar ativos automaticamente:

- quantidade aprovada na aquisição;
- quantidade e item conciliado na NF-e;
- quantidade informada na conferência física.

O fluxo aceita entregas parciais, registra avarias, faltas e itens inesperados e mantém uma linha do tempo auditável por conferência.

## Regras implementadas

- Um modelo de equipamento pode chegar antes da individualização dos ativos.
- Nenhum `Equipamento` é criado durante a conferência; a individualização permanece para a etapa própria.
- A soma planejada das remessas não pode ultrapassar a aquisição nem a linha da NF-e.
- Somente itens fiscais com correspondência de catálogo confirmada podem ser vinculados.
- Falta simples encerra a etapa como recebimento parcial e permite nova entrega.
- Avaria, excesso, item inesperado ou linha sem correspondência fiscal encerram como recebimento com divergência.
- Cada divergência guarda tipo, item, quantidade esperada, quantidade informada e observação.
- A idempotência existente continua impedindo entrada duplicada de estoque.
- A aquisição avança para `Em recebimento` ou `Recebida` conforme o total físico confirmado.
- A ordem de serviço aceita modelos ainda não individualizados e os marca como aguardando individualização.

## Interface

A tela da remessa passou a apresentar:

- comparação lado a lado entre compra, NF-e, remessa e físico;
- formulário de conferência com linguagem direta;
- registro opcional de item inesperado;
- histórico cronológico das conferências e divergências;
- bloqueio visual do formulário após encerramento definitivo.

Não há preços na tela operacional de recebimento e o vocabulário interno de arquitetura não é exposto ao usuário.

## Banco de dados

Migração criada: `compras.0011_divergenciarecebimentocompra_and_more`.

Ela adiciona a entidade de divergência, o vínculo da remessa com a linha fiscal, o modelo de equipamento ainda não individualizado e os snapshots das quantidades esperadas.

## Validação

- `manage.py check`: sem problemas.
- 4 cenários específicos de R7.F: aprovados.
- Regressão ampliada: 86 testes executados; 85 aprovados diretamente e o único caso bloqueado pela pasta temporária do ambiente passou ao ser repetido em diretório permitido. O erro adicional exibido era apenas a limpeza da mesma pasta bloqueada.
- Proteção entre empresas de documentos e acesso direto por identificador: aprovada na repetição isolada.
- `git diff --check`: sem erros de whitespace.

## Operação pendente

Nenhuma migração operacional, commit, push ou deploy foi executado. Antes de publicar, é necessário aplicar as migrações pendentes no ambiente correspondente pelo procedimento de release do projeto.
