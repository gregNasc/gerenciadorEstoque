# Release Gate R5 — Reutilizáveis individualizados / Balanças / SICK

## Status

**PRONTA PARA AUTORIZAÇÃO DE DEPLOY.**

Este gate não executa commit, push, migrations em produção nem deploy. Essas
ações dependem de autorização explícita.

## Escopo concluído

- Balanças permanecem em `Insumo`; não há conversão para `Equipamento`.
- Cada unidade reutilizável elegível possui patrimônio e estado individual:
  Operacional, SICK, Manutenção ou Inativo.
- O SICK existente aceita exatamente um alvo: equipamento ou unidade
  reutilizável individualizada.
- O banco impede SICK sem alvo, com dois alvos ou duas ocorrências ativas para
  a mesma unidade reutilizável.
- Admins e Gestores podem abrir SICK pelo Estoque de Insumos; a ação não é
  exibida para Operadores.
- Tenant, Empresa e Base são preservados em visualização, abertura,
  movimentações, histórico, comunicados e lembretes.
- Histórico de reutilizáveis é gravado em `HistoricoInsumo`.
- A ordem de serviço registra o insumo e o patrimônio sem criar equipamento
  fictício.
- O fluxo legado de equipamentos foi preservado.

## Migrations

1. `insumos.0049_status_ativo_individualizado_r5`
   - adiciona o estado individual;
   - converte `ativo=True` em `OPERACIONAL`;
   - converte `ativo=False` em `INATIVO`;
   - adiciona restrição dos estados válidos.
2. `estoque.0074_sick_alvo_generico_r5`
   - torna o equipamento opcional e protegido contra exclusão;
   - adiciona o vínculo opcional com a unidade reutilizável;
   - exige exatamente um alvo;
   - impede dois SICKs ativos para a mesma unidade reutilizável.

As migrations foram aplicadas do zero na base SQLite isolada usada pelos
testes. Não há remoção nem transformação destrutiva de dados existentes.

## Validação executada

- `python manage.py check`: aprovado.
- `python manage.py makemigrations --check --dry-run`: nenhuma mudança
  pendente.
- `git diff --check`: aprovado.
- compilação Python de `estoque`, `insumos` e `ordens_servico`: aprovada.
- suíte de impacto: **54 testes aprovados**.

A suíte cobre o fluxo legado de equipamentos, os novos reutilizáveis,
isolamento multi-tenant, permissões, ordens de serviço e templates afetados.

## Riscos conhecidos

- O novo vínculo é estrutural; a migration deve ser executada antes de servir
  o novo código.
- Após criar um SICK de reutilizável em produção, não é seguro reverter apenas
  a migration `0074`, pois o esquema anterior exige equipamento. Nesse caso, o
  rollback deve restaurar código **e** backup do banco.
- A ação de abertura fica dentro do modal de detalhes do Estoque de Insumos;
  a validação pós-deploy deve confirmar a submissão nesse contexto.
- O aviso local de `makemigrations --check` sobre PostgreSQL indisponível
  decorre do ambiente isolado; a verificação de estado concluiu com “No
  changes detected”.

## Deploy preparado

1. Criar backup lógico recuperável do PostgreSQL de produção.
2. Confirmar o commit de produção atual e a branch `main`.
3. Commitar a R5 na `main` e enviar ao repositório remoto.
4. Executar deploy no Render.
5. Confirmar no log a aplicação, nesta ordem, de:
   - `insumos.0049_status_ativo_individualizado_r5`;
   - `estoque.0074_sick_alvo_generico_r5`.
6. Somente após a aplicação das migrations, liberar tráfego ao novo código.

## Verificações pós-deploy

1. Abrir Estoque de Insumos como Admin e como Gestor de uma Base autorizada.
2. Abrir o detalhe de uma unidade reutilizável Operacional e confirmar a ação
   “Registrar ocorrência SICK”.
3. Criar uma ocorrência de teste e confirmar:
   - mudança da unidade para SICK;
   - aparição no módulo SICK;
   - Empresa, Base e patrimônio corretos;
   - criação de histórico e ordem de serviço.
4. Confirmar que Operador não vê a ação de abertura.
5. Confirmar que usuário de outro tenant não vê nem movimenta a ocorrência.
6. Executar uma transição até Manutenção e confirmar o estado individual.
7. Validar um SICK legado de equipamento, inclusive série, patrimônio,
   histórico e ações.
8. Consultar logs de erros e migrations no Render.

## Rollback

Se o deploy falhar antes de haver novos dados R5, reimplantar o commit anterior
e avaliar a reversão controlada das migrations. Se qualquer ocorrência SICK de
reutilizável já tiver sido criada, restaurar o backup do PostgreSQL junto com o
commit anterior. Nunca remover manualmente o vínculo para forçar downgrade.

