# Correção do seletor de equipamentos da Custódia

## Causa

O domínio de Custódia exige a capacidade explícita `CUSTODIA_PESSOAL` no
catálogo da empresa. A regra existia, mas a configuração não estava disponível
na tela do Catálogo da Empresa. Assim, equipamentos cadastrados na Base eram
corretamente recusados pela regra, porém o administrador não tinha como
habilitar seus modelos.

## Correção

- o Catálogo da Empresa agora permite marcar modelos individualizados como
  elegíveis para Custódia pessoal;
- a configuração é isolada por empresa, inclusive entre Inventory Brasil,
  LATAM e OXXO;
- o seletor da Nova Custódia identifica Empresa e Base de cada ativo e mostra
  somente os compatíveis com a Base selecionada;
- quando não houver equipamentos elegíveis, a tela informa a causa e oferece
  acesso direto ao Catálogo da Empresa;
- equipamentos já vinculados a uma Custódia vigente continuam indisponíveis;
- balanças continuam inelegíveis por padrão.

Para disponibilizar os equipamentos atuais da OXXO, um administrador deverá
abrir **Catálogo da empresa**, carregar **OXXO**, marcar os modelos desejados em
**Equipamentos elegíveis para Custódia pessoal** e salvar.

A regressão integrada de Catálogo, Custódia e `insumos` foi concluída com 132
testes aprovados.
