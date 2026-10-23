# R4.B — Identificadores flexíveis por tipo de ativo

## Entrega

O cadastro e a edição de equipamentos passaram a respeitar as capacidades do
produto no catálogo da empresa:

- `POSSUI_SERIE` e `SERIE_OBRIGATORIA` controlam o número de série;
- `POSSUI_PATRIMONIO` e `PATRIMONIO_OBRIGATORIO` controlam o patrimônio;
- produtos sem configuração explícita mantêm o comportamento legado, com os
  dois identificadores obrigatórios;
- valores preenchidos continuam únicos em todo o sistema;
- múltiplos ativos podem ficar sem série ou patrimônio quando a configuração
  do produto permitir;
- cada unidade possui uma observação operacional própria.

As regras são resolvidas considerando a empresa da Base selecionada. Portanto,
o mesmo produto pode exigir identificadores diferentes em empresas distintas.

## Compatibilidade e dados existentes

A migração `estoque.0072_equipamento_identificadores_flexiveis` torna os dois
identificadores anuláveis e converte apenas strings vazias em `NULL`. Nenhum
patrimônio ou número de série preenchido é alterado ou removido.

Se uma capacidade for desativada depois de existirem unidades cadastradas, o
identificador legado permanece visível e pode ser preservado em edições não
relacionadas. Novos valores incompatíveis com a configuração são bloqueados.

## Validação

- `manage.py check`: sem problemas;
- `makemigrations --check --dry-run`: nenhuma alteração pendente;
- 53 testes de capacidades, cadastro de equipamento, linhas móveis e Custódia:
  aprovados.

## Deploy

Executar as migrações antes de liberar o cadastro:

```text
python manage.py migrate
```

Não há exclusão de registros nem redefinição de senhas.
