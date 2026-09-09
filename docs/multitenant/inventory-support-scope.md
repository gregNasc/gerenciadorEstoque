# Suporte compartilhado — grupo Inventory

## Regra implantada

O checkbox **Suporte Inventory Brasil / LATAM / OXXO** mantém o usuário em sua
empresa e em suas Bases originais, mas permite que ele visualize, seja designado
e atenda chamados de Inventory Brasil, Inventory LATAM e OXXO.

O compartilhamento é dirigido por configuração persistida:

- `RelacionamentoEmpresa.compartilha_suporte_chamados=True`;
- relacionamento ativo;
- capability ativa e exata `CHAMADOS:ATENDER`.

A migração `0047_relacionamento_suporte_chamados` habilita a regra somente nos
relacionamentos direcionais de Inventory Brasil para Inventory LATAM e OXXO.
As duas pontas desses relacionamentos compõem o grupo atendido.

## Limites de segurança

- a empresa e a Base do perfil não são alteradas;
- a abertura de chamados continua usando apenas as Bases normais do usuário;
- o escopo ampliado não alcança estoque, equipamentos, SICK, transferências,
  empréstimos ou administração de usuários;
- empresas externas ao grupo não são incluídas;
- remover a flag ou a capability encerra o compartilhamento sem alteração de
  código.

## Validação automatizada

`chamados/test_inventory_support_scope.py` cobre usuário registrado em empresa
externa ao grupo e vinculado a uma única Base, candidatos a atendimento, limites
de abertura e ausência da configuração/capability.

