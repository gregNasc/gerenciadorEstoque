# R3.B — Dados de EPI

## Objetivo

Estruturar os dados específicos de equipamentos de proteção individual sem
misturar o cadastro técnico do EPI com o estoque físico de cada Base.

## Estrutura implementada

- `ProdutoEpi`: complementa exclusivamente um `Insumo` cuja natureza seja
  `EPI` e registra fabricante/importador e observações gerais.
- `CertificadoEpi`: registra o número do CA, sua validade e observações. O
  número é normalizado e único no sistema.
- `VarianteEpi`: representa tamanho, variante e código do item. Um mesmo EPI
  pode possuir várias variantes sem duplicar o CA.
- `LoteEpi`: registra lote, fabricação, validade física e observações na Base
  que detém o estoque. A variante e o certificado podem ser associados ao
  lote.

As validades do CA e do produto físico são independentes. Essa separação evita
que uma renovação de certificado altere retroativamente a validade de um lote.

## Consistência e isolamento

- Dados especializados só podem ser associados a insumos de natureza `EPI`.
- Variante e certificado associados a um lote devem pertencer ao mesmo
  produto EPI.
- A validade física não pode ser anterior à fabricação.
- A identificação do lote é única por Base, produto e variante.
- A consulta de lotes usa `InsumosTenantPolicy.epi_lots()`, mantendo o filtro
  por Bases autorizadas para o usuário e impedindo acesso entre tenants.

## Banco de dados

A migration `insumos/migrations/0040_dados_epi.py` cria as quatro entidades,
restrições de unicidade e o índice de consulta por Base, situação e validade
física. Ela é aditiva e não altera nem remove os registros existentes.

## Validação

- 7 testes específicos da R3.B aprovados.
- 70 testes do módulo `insumos` aprovados.
- `manage.py check` sem problemas.
- `makemigrations --check --dry-run` sem alterações pendentes.

## Fora do escopo desta subetapa

A R3.B entrega o núcleo de dados. Regras operacionais e interface de gestão de
CA pertencem à R3.C; alertas de vencimento pertencem à R3.D. Nenhum alerta,
deploy, commit ou envio ao repositório remoto foi executado nesta subetapa.
