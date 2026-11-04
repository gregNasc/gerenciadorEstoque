# K.2 / R7.A — Contrato de eventos e comunicação de Compras

**Data:** 28/10/2026  
**Branch:** `main`  
**Baseline implantado:** `458261980306b4bf2d5c360f7e2d3cc8a226275f`  
**Status:** aprovado localmente; não implantado

## Escopo realizado

- auditoria das transições de Aquisição, Remessa e Recebimento já existentes;
- definição de identificadores estáveis em `EventoCompraTipo`;
- alinhamento entre `EventoCompra.tipo` e `Comunicado.dados.evento`;
- preservação do payload operacional sem preços por padrão;
- validação de destinatários por tenant e Base;
- validação de idempotência de recebimento;
- validação de transação revertida sem evento ou comunicado;
- correção mínima de lock PostgreSQL no carregamento de SICK encontrada na
  regressão de Compras.

Não foram implementados cotação, escolha de fornecedor, importação de NF-e ou
novos estados de recebimento. Esses domínios permanecem subordinados às futuras
subetapas funcionais da R7.

## Contrato de eventos ativos

| Evento | Agregado | Destinatários atuais | Conteúdo externo permitido |
|---|---|---|---|
| `AQUISICAO_CRIADA` | Aquisição | Admins autorizados da empresa e autor | empresa, fornecedor e quantidade de itens; sem preço |
| `AQUISICAO_APROVADA` | Aquisição | Admins autorizados e cadastrador | estado da aquisição e fornecedor; sem preço |
| `REMESSA_CRIADA` | Remessa | Admins autorizados e usuários da Base destino | protocolo e Base; sem custo |
| `REMESSA_ENVIADA` | Remessa | Admins autorizados e usuários da Base destino | protocolo, Base e estado logístico |
| `REMESSA_CONFERIDA` | Remessa | Admins autorizados e usuários da Base destino | protocolo e resultado operacional |

O banco continua sendo a fonte oficial. O comunicado apenas aponta para a ação
persistida e não representa aprovação, aceite ou recebimento por si só.

## Segurança e isolamento

- outro tenant não recebe o comunicado;
- o acesso ao link continua protegido por `AquisicaoAccessPolicy` e
  `ComprasAccessPolicy`;
- `jose.barboza` pode receber aviso operacional no tenant, mas o título,
  mensagem e payload não contêm preço, custo ou valor unitário;
- DANFE/XML e detalhe financeiro continuam bloqueados pela policy financeira;
- o dispatcher externo não foi ativado nem alterado nesta etapa.

## Idempotência e consistência

- criação de comunicado permanece em `transaction.on_commit`;
- uma transação revertida não deixa `Aquisicao`, `EventoCompra` ou `Comunicado`;
- `RecebimentoRemessa` mantém unicidade por `remessa + idempotency_key`;
- repetir a confirmação com a mesma chave retorna o mesmo recebimento e não
  duplica `REMESSA_CONFERIDA` nem o comunicado;
- mudanças de estado inválidas continuam bloqueadas antes de novo evento.

## Correção PostgreSQL da regressão

A suíte completa revelou que `_carregar_sick` aplicava `FOR UPDATE` também aos
dois alvos opcionais de SICK (`equipamento` ou `ativo_insumo`) carregados por
junção externa. PostgreSQL recusa lock no lado anulável.

A consulta agora usa:

```python
Sick.objects.select_for_update(of=('self',)).select_related(...)
```

O registro SICK é bloqueado primeiro e o alvo concreto continua sendo bloqueado
separadamente em seguida. A concorrência permanece protegida sem tentar bloquear
uma linha inexistente.

## Arquivos desta subetapa

- `compras/eventos.py`
- `compras/services.py`
- `compras/test_eventos_comunicacao_k2.py`
- `estoque/services/sick_service.py`
- `docs/relatorio_k2_eventos_compras.md`

As alterações ainda não implantadas de K.1 permanecem preservadas na mesma
árvore de trabalho e estão documentadas em
`docs/relatorio_k1_badge_solicitacoes.md`.

## Migrations

Nenhuma. `EventoCompra.tipo` continua compatível com os registros existentes.

## Testes executados

### Reprodução antes do patch

```text
3 testes K.2
1 aprovado
2 falharam como esperado:
- comunicado de Aquisição sem dados.evento
- comunicado de Remessa sem dados.evento
```

### Contrato K.2 após o patch

```text
3 / 3 aprovados
```

### Integração Compras + R6 + K.1 + K.2

```text
30 / 30 aprovados em 43,956 s
```

### Suíte completa de Compras

Primeira execução:

```text
35 aprovados
1 erro PostgreSQL no lock de SICK
```

Após a correção:

```text
36 / 36 aprovados em 10,464 s
```

### Checks

```text
python manage.py check
System check identified no issues.

python manage.py makemigrations --check --dry-run
No changes detected.

git diff --check
Sem erro; apenas avisos informativos de conversão LF/CRLF.
```

## Desempenho e qualidade

- nenhuma consulta nova no request HTTP;
- nenhuma mensagem externa síncrona;
- nenhum loop adicional por destinatário fora do dispatcher existente;
- identificadores centralizados reduzem divergências e facilitam suporte;
- payload mínimo diminui risco de vazamento e simplifica entendimento;
- correção de lock evita falha em produção e preserva concorrência.

## Deploy e pós-deploy

Deploy não executado. Quando autorizado, publicar K.1 e K.2 juntos e validar:

1. badge da R6 por dois tenants;
2. criação e aprovação de uma Aquisição de teste autorizada;
3. `Comunicado.dados.evento` correspondente ao histórico;
4. remessa e conferência idempotente;
5. acesso negado ao detalhe/XML por usuário sem permissão financeira;
6. transição do SICK para manutenção sem erro `FOR UPDATE`.

## Rollback

- reverter os patches de K.2 restaura o payload anterior;
- não há rollback de banco;
- eventos históricos permanecem válidos;
- K.1 pode ser revertido separadamente.

## Próxima subetapa proposta

R7.B — auditar e evoluir Fornecedores/Cotações como uma unidade funcional
independente. Eventos de cotação só serão adicionados depois que a transição de
domínio correspondente existir e estiver aprovada.

**STOP — aguardando autorização.**
