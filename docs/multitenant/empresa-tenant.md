# Etapa 5 — Preparar Empresa como tenant

Data do checkpoint: 2026-09-05.

## Objetivo

Adicionar metadados de tenant a `Empresa` sem alterar as regras atuais de
autorização, sem tornar campos de transição obrigatórios e sem criar interface.

## Alterações

O model `Empresa` recebeu:

- `slug`: `SlugField` opcional, indexado e ainda sem constraint de unicidade;
- `ativa`: indicador com valor padrão `True`;
- `criado_em`: timestamp automático de criação;
- `atualizado_em`: timestamp automático de atualização.

O `slug` foi classificado como campo técnico para não ser convertido em caixa
alta pela normalização global dos textos de negócio.

## Migration e backfill

A migration `estoque.0043_empresa_metadados_tenant` é aditiva e executa as
operações na seguinte ordem:

1. adiciona os metadados compatíveis;
2. mantém `slug` aceitando `NULL` e vazio;
3. gera slugs para as empresas existentes com `slugify`;
4. resolve nomes repetidos com sufixos numéricos determinísticos;
5. usa `empresa-<pk>` quando o nome não produz um slug;
6. valida que o backfill não deixou slug vazio ou duplicado.

O backfill preserva um slug já existente, podendo ser executado novamente sem
substituí-lo. A operação reversa limpa os slugs antes da remoção dos campos.

A unicidade ainda não foi endurecida no schema. Essa decisão mantém a evolução
compatível e separa `ADICIONAR/POPULAR/VALIDAR` do futuro endurecimento da
constraint.

## Validação do banco local

A migration foi aplicada ao banco de desenvolvimento. Resultado após o
backfill:

```text
empresas: 3
sem slug: 0
slugs duplicados: 0
inativas: 0
sem timestamps: 0
```

## Testes

Foram adicionados três testes para validar:

- metadados padrão de novas empresas;
- compatibilidade temporária de slug vazio;
- preservação de slug técnico em minúsculas e do nome de exibição.

Suíte relacionada:

```powershell
python manage.py test estoque.test_empresa_tenant_metadata estoque.test_text_normalization estoque.test_multitenant_contract estoque.test_user_access_profiles --keepdb -v 1
```

Resultado: 22 testes; 15 aprovados e 7 falhas esperadas do contrato; suíte OK.

Validações estruturais:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
```

Resultado: zero inconsistências e nenhuma alteração de model sem migration.

A suíte completa do app `estoque` executou 172 testes: 163 aprovados, 7 falhas
esperadas e as mesmas 2 falhas antigas de UI registradas na Etapa 4. Não houve
regressão nova relacionada aos metadados de tenant.

## Solicitação operacional adicional

Por solicitação explícita, a conta local `admin` foi promovida com
`is_superuser=True` e `is_staff=True`. A conta permanece ativa e o hash da senha
foi verificado antes e depois da atualização, sem alteração.

## Compatibilidade e pendências

- regras de Admin, Gestor e Operador não foram alteradas;
- nenhuma Empresa foi desativada;
- nenhuma senha foi modificada;
- novos registros ainda podem ter `slug` nulo ou vazio durante a transição;
- unicidade e obrigatoriedade do slug deverão ser endurecidas somente após a
  validação das próximas etapas.

## Próxima etapa

Etapa 6 — Corrigir conceito de Admin.
