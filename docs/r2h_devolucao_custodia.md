# R2.H — Devolução de Custódia

## Escopo implementado

- registro histórico de cada ocorrência de devolução;
- data, motivo, observação, responsável pelo recebimento e usuário registrador;
- classificação obrigatória de todos os itens ainda pendentes;
- situação por item: `DEVOLVIDO` ou `FALTANTE`;
- condição individual obrigatória para item devolvido;
- devolução parcial preservando o item faltante como vigente;
- finalização automática quando não restam itens pendentes;
- liberação do ativo devolvido sem excluir a Custódia ou seus itens históricos;
- suporte à devolução posterior de um item antes classificado como faltante;
- sincronização do responsável legado dos equipamentos liberados.

## Integridade

O serviço `CustodiaDevolucaoService.registrar` bloqueia a Custódia e seus itens
pendentes durante a operação. A ocorrência, a classificação dos itens, a
liberação e a transição de status são executadas em uma única transação.

Um item pode aparecer como faltante em mais de uma ocorrência, mas só pode ser
classificado como devolvido uma única vez. A constraint de banco também impede
que um item devolvido permaneça vigente.

## Decisão sobre anexos

Fotos e anexos não foram incluídos nesta subetapa. O plano condiciona esses
arquivos a aprovação específica, e a política de armazenamento privado e
retenção ainda será definida antes de introduzir dados potencialmente sensíveis.

## Fora do escopo

- telas e rotas do fluxo de Custódia;
- Termo de Entrega (R2.I);
- Termo de Devolução (R2.J);
- assinatura eletrônica e DocuSign.

## Validação

- 9/9 testes específicos da devolução aprovados;
- 90/90 testes de regressão R2.A–R2.H e dependências aprovados;
- migrations 0066–0068 aplicadas com sucesso no banco de teste;
- `makemigrations --check --dry-run`: nenhuma alteração pendente;
- `manage.py check`: nenhuma inconsistência.

No ambiente isolado, o aplicativo `daphne` foi removido apenas da lista de apps
do processo de teste porque a criação do socket interno do `asyncio` é bloqueada
pelo sandbox. As configurações persistentes do projeto não foram alteradas.
