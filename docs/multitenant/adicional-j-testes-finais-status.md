# Adicional J — Testes finais

## Status

Concluído em 29/09/2026.

## Suíte dedicada

Foi criada a suíte
`estoque.test_multitenant_final_regression_stage_j`, com um cenário integrado
entre dois tenants externos e o grupo Inventory.

### Cenários comprovados

- tenant externo criado pelo onboarding permanece inativo e fail-closed;
- tenant novo inicia com zero categorias, produtos e seções documentais;
- somente os módulos escolhidos ficam marcados como habilitados;
- Tenant A usa `SICK → Manutenção` e `Equipamentos → Máquinas`;
- Tenant B usa `SICK → Oficina` e `Equipamentos → Ativos`;
- a terminologia de A e B permanece independente no serviço e na interface;
- produto de A não aparece no catálogo ou Dashboard de B;
- produto de A não aparece no grupo Inventory;
- o produto só passa a B após categoria compatível e compartilhamento explícito;
- documento de A não aparece na listagem de B;
- download direto do documento de A por ID retorna 404 para B;
- Inventory Brasil, Inventory LATAM e OXXO permanecem no escopo somente por
  relacionamentos e vínculos adicionais explícitos;
- tenants externos não entram no escopo do grupo Inventory;
- Auditorias desabilitada remove o link do menu e bloqueia página e endpoint
  de escrita com HTTP 403;
- Estoque permanece habilitado quando Auditorias está desabilitada.

Resultado da suíte dedicada: **6 testes aprovados**.

## Critérios de aceite

- [x] nova empresa inicia sem catálogo global;
- [x] nova empresa inicia sem documentação global;
- [x] módulos são escolhidos manualmente;
- [x] categorias são tenant-specific;
- [x] produtos são tenant-aware;
- [x] filtros do Dashboard são tenant-aware;
- [x] KPIs não dependem das quatro categorias históricas;
- [x] `SICK` pode aparecer como `Manutenção`;
- [x] nomes personalizados aparecem consistentemente;
- [x] Documentação possui seções configuráveis;
- [x] “Manuais de equipamentos” pode aparecer como “Manual Operacional”;
- [x] Auditorias pode ser desligada mantendo Estoque;
- [x] Cadastro pode ser controlado;
- [x] Usuários pode ser controlado;
- [x] feature desabilitada não pode ser acessada por URL;
- [x] Tenant A não vê produto do Tenant B;
- [x] Tenant A não vê documento do Tenant B;
- [x] Grupo Inventory preserva o comportamento necessário;
- [x] nenhuma regra de autorização revisada utiliza fallback global permissivo;
- [x] autorização não depende do nome textual do cliente;
- [x] Superuser consegue editar a configuração posteriormente;
- [x] estratégia segura de migrations preservada;
- [x] testes existentes continuam passando;
- [x] novos testes de isolamento/configuração passam;
- [x] `python manage.py check` passa;
- [x] `python manage.py makemigrations --check` passa.

## Migrations

O Adicional J não criou nem alterou migrations. As migrations de dados do
adicional multi-tenant preservam dados históricos quando a reversão destrutiva
não seria segura, usando reversão explícita ou `RunPython.noop`; alterações de
schema continuam sob o mecanismo reversível do Django.

## Validação executada

- suíte dedicada J: **6 testes aprovados** em 2,025 s;
- bateria consolidada dos critérios: **96 testes aprovados** em 94,718 s;
- suíte completa: **632 testes aprovados** em 833,552 s;
- `python manage.py check`: sem problemas;
- `python manage.py makemigrations --check --dry-run`: nenhuma alteração;
- `git diff --check`: sem erros de conteúdo; apenas avisos de LF/CRLF do Git
  no Windows.

## Resultado final

Todos os critérios de aceite do adicional de configuração total por empresa
foram cobertos e aprovados. O backend mantém códigos técnicos compartilhados,
enquanto módulos, terminologia, categorias, catálogo e documentação são
resolvidos por tenant e compartilhados somente por configuração explícita.
