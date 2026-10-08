# R2.C — Elegibilidade para Custódia

## Estado

Subetapa concluída localmente em 08/10/2026.

## Escopo entregue

- capacidade tenant-aware `CUSTODIA_PESSOAL` reutilizando o catálogo existente;
- equipamentos somente são elegíveis mediante capacidade explícita e ativa no
  catálogo da própria empresa;
- chips/linhas somente são elegíveis quando o produto de linha independente da
  empresa possui, simultaneamente, as capacidades `ATIVO_LINHA_MOVEL` e
  `CUSTODIA_PESSOAL`;
- consultas falham fechadas para empresa inválida, catálogo inativo, capacidade
  inativa e tipos desconhecidos;
- não existe comparação por descrição ou categoria do produto;
- Balanças permanecem inelegíveis por padrão e não foram migradas para o domínio
  de Equipamentos.

## Migration

Nenhuma. A estrutura genérica `CapacidadeCatalogoProdutoEmpresa` já persiste
códigos de capacidade; R2.C adiciona somente o código de domínio e o serviço de
resolução.

## Limite desta subetapa

Ainda não foram criados:

- telas para configuração da capacidade de Custódia;
- modelo de Custódia ou itens de Custódia;
- entrega, devolução, termos, DocuSign ou notificações;
- alteração do campo legado `responsavel`.

## Segurança e compatibilidade

A elegibilidade é isolada por empresa exata, inclusive dentro do Grupo
Inventory. Administradores com acesso a múltiplas empresas não transformam o
catálogo dessas empresas em um catálogo compartilhado.

## Validação

- testes direcionados R2.C: 6/6;
- R2.A/R2.B + R2.C + catálogo fail-closed + linhas móveis: 41/41;
- `python manage.py check`: aprovado;
- `python manage.py makemigrations --check --dry-run`: nenhuma alteração;
- `git diff --check`: aprovado (somente avisos de normalização LF/CRLF).

## STOP

Não houve commit, push, migration no banco local/produção ou deploy.
Não iniciar R2.D sem autorização.
