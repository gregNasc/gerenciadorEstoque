# R2.E — Itens de Custódia

## Estado

Subetapa implementada localmente em 08/10/2026.

## Escopo entregue

- uma Custódia pode conter múltiplos itens individualizados;
- cada item referencia exatamente um Equipamento ou uma Linha Móvel;
- somente ativos explicitamente elegíveis pela R2.C são aceitos;
- empresa e Base do ativo devem corresponder à Custódia;
- o mesmo ativo não pode ser repetido dentro da mesma Custódia;
- a referência do item histórico é imutável após o cadastro;
- condição e observação são registradas por item;
- snapshots mínimos preservam descrição, patrimônio, série, IMEI quando
  disponível, telefone, ICCID e operadora sem duplicar todo o ativo.

## Migration

`estoque.0066_itemcustodia` é aditiva e cria a tabela de itens, constraints e
índices. Nenhuma estrutura legada é removida ou alterada.

## Limite desta subetapa

Ainda não foram criados:

- exclusividade entre Custódias ativas, reservada à R2.F;
- telas, formulários ou endpoints;
- devolução ou condição de devolução;
- Termos de Entrega/Devolução;
- DocuSign e notificações;
- compatibilidade com o campo legado `responsavel`.

## Segurança

O modelo valida novamente empresa, Base e capacidade tenant-aware, mesmo quando
o chamador fornece diretamente uma chave primária. PIN e PUK não são copiados
para snapshots. ICCID permanece disponível apenas no domínio e deverá respeitar
a policy de visualização quando as telas/documentos forem implementados.

## Validação

- testes direcionados R2.E: 9/9;
- R2.A–R2.E + catálogo fail-closed + linhas móveis: 58/58;
- `python manage.py check`: aprovado durante os testes.

## STOP

Não houve commit, push, migration aplicada no banco local/produção ou deploy.
Não iniciar R2.F sem autorização.
