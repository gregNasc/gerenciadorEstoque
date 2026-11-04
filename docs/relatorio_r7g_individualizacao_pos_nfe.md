# R7.G — Individualização pós-NF

## Resultado

Equipamentos recebidos por modelo e quantidade agora podem ser transformados em unidades físicas individualizadas, uma por vez, somente após a conferência do recebimento.

## Regras implementadas

- A NF-e e a remessa identificam o modelo e a quantidade, mas não inventam identificadores físicos.
- Cada unidade criada fica vinculada simultaneamente ao item da aquisição e ao item da remessa.
- A quantidade de unidades individualizadas nunca pode ultrapassar a quantidade recebida sem avaria.
- Quantidades fracionadas não podem gerar equipamentos individualizados.
- A unidade é cadastrada obrigatoriamente na Base que recebeu a remessa.
- Patrimônio e série seguem as capacidades configuradas para o modelo na empresa.
- IMEI continua opcional; quando informado, deve conter 15 dígitos e ser único.
- Patrimônio, série e IMEI respeitam as verificações globais de duplicidade já existentes.
- Modelos desabilitados para individualização são recusados.
- A criação registra histórico do equipamento, vínculo de aquisição e evento auditável da remessa.
- O valor originado do documento é preservado internamente, mas não aparece nas telas operacionais.

## Acesso e isolamento

- Admin e Gestor com acesso operacional à Base podem individualizar unidades.
- `jose.barboza` pode individualizar equipamentos, mas não recebe acesso a preços, valores, NF-e ou telas financeiras.
- A fila apresenta somente recebimentos das Bases autorizadas para o usuário.
- Um Admin de outra empresa recebe `404` ao tentar acessar o item diretamente.

## Interface

Foi criada uma fila em **Cadastros → Identificar recebimentos** com:

- modelo e Base de destino;
- quantidade recebida;
- quantidade já identificada;
- quantidade ainda pendente;
- acesso ao cadastro unitário.

O formulário mostra apenas os identificadores aplicáveis ao modelo e lista as unidades já concluídas. Nenhum campo financeiro é renderizado.

## Banco de dados

Migração criada: `compras.0012_vinculoequipamentoaquisicao_item_remessa`.

Ela adiciona ao vínculo de aquisição a referência ao item físico recebido, preservando compatibilidade com os vínculos antigos.

## Validação

- `manage.py check`: sem problemas.
- `makemigrations --check --dry-run`: nenhuma alteração pendente.
- 4 testes específicos de R7.G: aprovados.
- Regressão integrada de Compras, equipamentos, linhas móveis e terminologia: 100 testes aprovados.
- IMEI opcional, limite físico, José Barboza e isolamento entre empresas cobertos por testes.

## Operação pendente

Nenhuma migração operacional, commit, push ou deploy foi executado. A migração `0012`, junto das migrações anteriores ainda não aplicadas no ambiente de destino, deve seguir o procedimento normal de release.
