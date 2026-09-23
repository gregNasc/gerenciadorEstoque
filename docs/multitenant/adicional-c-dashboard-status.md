# Adicional C — Categorias e Dashboard (22/09/2026)

O Dashboard utiliza categorias ativas e catálogo explícito por empresa. O
seletor organizacional exige vínculo adicional do Admin e capability
OPERACAO:ADMINISTRAR; compartilhar apenas equipamentos não amplia esse seletor.
O Superuser mantém o escopo da plataforma. Produtos, categorias e equipamentos
são correlacionados à mesma empresa, inclusive na consulta conjunta do grupo.

O rótulo do seletor utiliza TermoEmpresa, chave `empresa`, com padrão `Empresa`.
Pode ser editado no painel Superuser, na configuração de módulos de cada empresa.
A migration 0055 preserva `Inventory` como configuração dos tenants históricos.
A apresentação de um tenant selecionado usa sua própria configuração.

O checklist deixou de depender das quatro categorias históricas. As linhas,
campos enviados, saldos, equipamentos disponíveis e limites são obtidos de
`CategoriaEquipamentoEmpresa` e do catálogo ativo da mesma empresa. A margem
por quantidade de pessoas e a categoria usada como referência de capacidade
são configurações opcionais por tenant. Categorias sem configuração não são
inferidas e produtos fora do catálogo são recusados.

O Tory reconhece o nome e os aliases cadastrados no tenant, aplica o catálogo
fail-closed e usa a categoria de referência configurada para capacidade. Um
alias cadastrado em outra empresa não é reconhecido. Compartilhamento explícito
de equipamentos continua respeitando sua capability própria e não amplia o
seletor organizacional do Dashboard.

A migration 0056 preserva explicitamente, apenas para o Grupo Inventory, os
aliases históricos, a margem de cinco itens para Coletores e a referência de
capacidade. Empresas externas não recebem essas regras. A migration 0038 remove
as choices globais do registro quantitativo do checklist.

## Validação local

- Suíte completa: 587 testes aprovados.
- Validação integrada de Dashboard, checklist, Tory e migrations: 71 testes aprovados.
- Verificação Django sem erros; nenhuma migration pendente de geração.
- Migrations `estoque.0056` e `insumos.0038` aplicadas no banco local.
- Hash rápido usado exclusivamente no processo dos testes; senhas reais intactas.
- Sem commit, push ou deploy nesta execução.

## Status

O Adicional C está concluído no escopo previsto. Ocorrências históricas restantes
na documentação pertencem ao Adicional F; a auditoria global de exports, relatórios
e textos pertence ao Adicional I. O próximo bloco do plano é o Adicional D —
Módulos independentes — e não foi iniciado nesta execução.
