# R5 — Reutilizáveis individualizados, Balanças e SICK

## Decisões preservadas

- Balanças permanecem cadastradas como `Insumo`.
- Cada unidade física reutilizável é representada por
  `AtivoInsumoIndividualizado`.
- Individualização não cria Custódia pessoal automaticamente.
- O SICK existente será evoluído; não será criado um segundo módulo de
  manutenção.

## R5.A — Estado individual da unidade

Implementado:

- estado próprio por patrimônio: Operacional, SICK, Manutenção ou Inativo;
- migração compatível, convertendo registros legados ativos em Operacional e
  inativos em Inativo;
- campo legado `ativo` sincronizado para preservar consultas existentes;
- estoque e catálogo exibem o estado de cada unidade;
- unidades inativas continuam visíveis no detalhamento, sem serem confundidas
  com unidades disponíveis.

## R5.B — alvo genérico do SICK

O domínio do SICK aceita, com exclusividade protegida no banco, um
`Equipamento` **ou** um `AtivoInsumoIndividualizado`. A unidade reutilizável:

- permanece um insumo e nunca é convertida em equipamento;
- herda a Base e o tenant do cadastro individual;
- alterna entre Operacional, SICK, Manutenção e Inativo pelo mesmo serviço de
  domínio já usado pelo módulo SICK;
- registra histórico em `HistoricoInsumo` e uma linha patrimonial na ordem de
  serviço, sem criar equipamento fictício;
- não pode possuir duas ocorrências SICK ativas simultaneamente.

Na interface, Admins e Gestores podem abrir a ocorrência diretamente no
detalhamento do Estoque de Insumos quando a unidade estiver Operacional. O
registro passa a aparecer no fluxo SICK existente, com identificação do tipo
de ativo, Base, patrimônio, linha do tempo e ações de manutenção. Operadores
não recebem a ação de abertura no Estoque de Insumos.

Os filtros de tenant e Base abrangem os dois tipos de alvo, inclusive no fluxo
terceirizado, e os lembretes de manutenção prevista usam a identificação
genérica do ativo.
