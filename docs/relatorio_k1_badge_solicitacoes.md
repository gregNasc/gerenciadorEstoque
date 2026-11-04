# K.1 — Badge e notificações internas da Solicitação Unificada

**Data:** 27/10/2026  
**Branch / baseline:** `main` / `458261980306b4bf2d5c360f7e2d3cc8a226275f`  
**Status:** aprovado localmente; não implantado

## Escopo realizado

- substituição do contador global do modelo legado pela Solicitação Unificada R6;
- contagem somente de estados abertos e acionáveis;
- escopo aplicado por tenant e Base com `InsumosTenantPolicy`;
- acesso ao contador limitado a Admin, Superuser e grupo funcional Compras;
- Gestor sem competência de decisão recebe contador zero;
- tenant com módulo Insumos desabilitado não executa nem expõe a contagem;
- badge movido de Transferências/Pedidos legados para o menu Solicitações;
- total de Transferências deixou de somar solicitações da R6;
- remoção de notificações de manutenção e limpeza de expirados do context processor;
- centralização da decisão funcional em `SolicitacaoConsultaService`.

## Estados contados

```text
PENDENTE
RECEBIDA_COMPRAS
EM_ANALISE
APROVADA
EM_COMPRA
PEDIDO_REALIZADO
RECEBIDA
```

`REPROVADA` e `FINALIZADA` não entram no badge.

## Eficiência e clareza

- uma única consulta agregada para a contagem autorizada;
- queryset filtrado no banco, sem loop por solicitação;
- usuários sem competência recebem `QuerySet.none()`;
- nenhuma escrita, limpeza ou criação de comunicado durante a renderização;
- nenhum contador duplicado entre R6 e o fluxo legado;
- badge apresentado junto ao menu que realmente abre a Solicitação Unificada.

## Isolamento e permissões

- Admin conta somente solicitações das empresas acessíveis;
- Compras com perfil de Gestor conta somente Bases vinculadas;
- outro tenant não influencia o contador;
- Gestor comum não recebe tarefas administrativas;
- solicitações legadas não entram no badge;
- nenhuma informação financeira foi acrescentada ao menu ou aos comunicados;
- a proteção de `jose.barboza` permanece inalterada.

## Testes

### K.1 dirigido

```text
python manage.py test estoque.test_badge_solicitacoes_r6_k1 --keepdb --noinput
5 testes aprovados
```

Cenários:

- R6 versus modelo legado;
- isolamento entre tenants;
- escopo de Base para Compras;
- Gestor sem competência;
- context processor sem escrita;
- badge em Solicitações e ausente de Transferências.
- feature flag de Insumos desligada sem consulta desnecessária.

### Regressão R6 + K.1

```text
python manage.py test \
  insumos.tests.SolicitacaoInsumoFluxoTests \
  estoque.test_badge_solicitacoes_r6_k1 \
  --keepdb --noinput

17 testes aprovados em 58,632 s
```

### Checks

```text
python manage.py check
System check identified no issues.

python manage.py makemigrations --check --dry-run
No changes detected.
```

## Banco de testes

A base descartável `test_estoque_render_dump` apresentava histórico antigo
inconsistente (`insumos.0049` antes de `insumos.0048`). Somente essa base de
testes foi recriada. Todas as migrations foram aplicadas em ordem, inclusive
`integracao.0010`, sem alteração na base local operacional ou em produção.

## Arquivos alterados

- `insumos/services/solicitacao_service.py`
- `insumos/views/solicitacoes.py`
- `estoque/context_processors.py`
- `estoque/templates/estoque/base.html`
- `estoque/test_badge_solicitacoes_r6_k1.py`
- `docs/auditoria_k0_r6_r7.md`
- `docs/relatorio_k1_badge_solicitacoes.md`

## Migrations

Nenhuma.

## Riscos e operação

- `notificar_manutencoes_previstas` já possui management command próprio e deve
  permanecer fora do request HTTP;
- a limpeza física de comunicados expirados não ocorre mais ao abrir páginas;
  os registros expirados continuam invisíveis pela regra `expira_em` e a
  política operacional de limpeza deve ser definida em K.5, fora do worker web;
- e-mail e WhatsApp permanecem desligados/não homologados e não foram alterados.

## Deploy

Não executado. Em futuro deploy autorizado:

1. publicar o commit aprovado;
2. executar o build normal e `migrate` (sem migration nova desta etapa);
3. acessar como Admin/Compras de dois tenants diferentes;
4. conferir que o badge aparece somente em Solicitações e respeita o escopo;
5. finalizar uma solicitação e confirmar a redução do contador;
6. conferir que Transferências não incorpora o número da R6.

## Rollback

Reverter o patch de K.1 restaura o contador legado. Não há rollback de banco.

**Próxima subetapa proposta:** K.2, junto da primeira subetapa funcional
autorizada da R7, para definir eventos e destinatários sem antecipar cotação,
NF-e ou recebimento ainda não implementados.

**STOP — aguardando autorização.**
