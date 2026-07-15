# Análise pré-implementação — bindings operacionais Inventory Planning

Data da análise: 15/07/2026.

## 1. Diagnóstico do modelo atual

Os catálogos e eventos externos são armazenados por `external_id`, origem e
timestamps de sincronização. `PlanningClientBinding` resolve um cliente externo
para `insumos.Cliente`; `PlanningRegionBinding` resolve uma regional externa
para uma única `estoque.Base`; `InventoryPlanningEventBinding` garante a
idempotência evento PAI → `Inventario`.

O materializador atual exige os dois bindings simples. Primeiro rejeita FILHO
para criação direta, depois valida tipo, loja, cliente e regional, e finalmente
cria ou atualiza o inventário. A base é obtida exclusivamente de
`PlanningRegionBinding`, sem considerar o cliente. Isso é insuficiente quando a
mesma regional possui operação regular e OXXO.

Os 1.773 PAI de produção estão `PENDING/client_binding_missing` porque não há
`PlanningClientBinding`. Depois que clientes fossem vinculados, o próximo erro
seria `region_binding_missing`, pois também não há bindings de regionais. Os 503
FILHO em `NOT_APPLICABLE` estão coerentes com a fase atual.

## 2. Dados disponíveis para resolução

O evento contém `external_id`, status, `plannedAt`, métricas, `importData`, tipo,
`store`, `client` e `region`. A loja sincronizada contém código, número, nome,
apelido, cidade, UF e relacionamentos com cliente e regional. O cliente contém
código, nome fantasia, razão social e segmento. A regional contém nome e UF.

Sinais úteis, mas não definitivos:

- código/número da loja;
- código, nome fantasia e razão social do cliente;
- nome e UF da regional;
- sigla e nome do cliente local;
- prefixo `OXXO`, sufixo operacional `X` e aliases explícitos;
- bindings previamente confirmados.

Nenhum desses sinais isolados autoriza criar vínculo definitivo.

## 3. Confirmação contra os cadastros locais

O banco local consultado possui 42 bases e 619 clientes. Foram encontradas 10
bases terminadas em `X`:

```text
OXXO SP INT CPN X
OXXO SP INT JUNDIAI X
OXXO SP INT PIRACICABA X
OXXO SP INT SOROCABA X
OXXO SP INT VALE X
OXXO SP LESTE AND X
OXXO SP LESTE GRU X
OXXO SP LESTE X
OXXO SP LITORAL X
OXXO SP SUL X
```

Para CPN coexistem `SP INT CPN` e `OXXO SP INT CPN X`. Em SP LESTE existem três
bases OXXO, logo até a regra prefixo/sufixo pode produzir mais de um candidato.

Também existem clientes locais distintos:

```text
OXX — MERCADO OXXO (GRUPO NÓS)
OXO — MERCADO OXXO (GRUPO NÓS) - SISTEMA ANTIGO
OXC — OXXO (CHILE)
OXD — OXXO (CD PAR)
OXP — OXXO (PERU)
```

Conclusão: `icontains`, nome normalizado ou palavra `OXXO` não podem confirmar
cliente ou base silenciosamente.

## 4. Proposta final de models

### `PlanningClientBinding`

Continua necessário. `planning_client` permanece único; `local_client` deve
passar de `OneToOneField` para `ForeignKey`, permitindo que mais de um cadastro
externo confirmado aponte para o mesmo cliente local. Serão adicionados
`source`, `is_active` e `updated_at`. O acesso reverso pelo planejamento
(`planning_client.local_binding`) permanece compatível.

### `PlanningRegionBinding`

Continua útil como fallback para regionais realmente inequívocas. Serão
adicionados `source`, `is_active` e `updated_at`. O resolver só aceitará o
fallback quando o binding estiver ativo, a base coincidir com o candidato
regular inequívoco e não houver binding combinado para o par.

### `PlanningOperationalBaseBinding`

Novo model confirmado e auditável:

```text
planning_client + planning_region → local_base
source: MANUAL | SUGGESTED | RULE
reason
is_active
confirmed_by / confirmed_at / updated_at
```

Haverá constraint única para `(planning_client, planning_region)`. O vínculo
combinado ativo terá precedência absoluta sobre o regional simples.

### Execuções de sincronização

`InventoryPlanningSyncRun.Status` receberá `STALE`. Runs interrompidos serão
`FAILED/INTERRUPTED`; runs abandonados só serão marcados `STALE` por comando
explícito e após a idade mínima configurada.

## 5. Migrations

Uma migration aditiva deverá:

1. alterar `PlanningClientBinding.local_client` para `ForeignKey`;
2. adicionar auditoria/ativação aos bindings atuais;
3. criar `PlanningOperationalBaseBinding` e sua constraint;
4. adicionar as permissões `gerenciar_mapeamentos_planning` e
   `executar_materializacao_planning`;
5. adicionar `STALE` às choices do run.

Não haverá migration de dados baseada em nome. Como produção não possui
bindings atuais, não existe vínculo a converter. Em ambientes que já possuam
bindings, eles serão preservados ativos e reavaliados pelo resolver antes do
uso como fallback.

## 6. Normalização e sugestões

Um único serviço fará normalização Unicode, remoção de acentos, caixa alta e
espaços. Funções controladas poderão retirar prefixo `OXXO` e sufixo `X` apenas
para comparação. Aliases como `CPN ↔ CAMPINAS` serão explícitos.

Sugestões de cliente usarão código de loja/sigla, nomes normalizados, aliases e
similaridade. Sugestões de base usarão regional, cliente local confirmado,
prefixo OXXO, sufixo X e operação regular. Cada candidato terá score, confiança
e motivo.

Sugestões nunca gravam bindings. Confirmação unitária exige ação humana.
Confirmação em lote aceitará apenas recomendação única de alta confiança,
recalculada no servidor no momento do POST.

## 7. Ordem de resolução

1. cliente externo com binding ativo;
2. binding combinado ativo cliente + regional;
3. binding regional ativo somente se inequívoco para a operação;
4. sugestão calculada, usada apenas para a tela;
5. pendência `operational_base_binding_ambiguous` ou
   `operational_base_binding_missing`.

O materializador nunca selecionará o primeiro candidato.

## 8. Propriedade dos campos

Fonte de planejamento: cliente, loja, base operacional confirmada, data/início
previsto, localização, tipo, pessoas previstas, observação, ponto de encontro e
previsão de peças.

Fonte local: início/fim real, contagem, total real de peças, status operacional
avançado, checklists, consumos, equipamentos, insumos, custos, responsável e
ajustes manuais da execução. Na criação, os campos planejados inicializam o
inventário. Depois que a execução avançar, a integração atualizará somente os
espelhos de previsão (`inicio_previsto`, `equipe_plan`, `previsao_pecas`), sem
regravar cadastro ou execução.

Cancelamento e remoção externos não excluem inventário nem histórico local.

## 9. Tela administrativa

A tela usará apenas combinações cliente/regional que impactam eventos PAI,
evitando produto cartesiano de 319 × 25. Terá:

- clientes pendentes, candidatos, confiança e eventos afetados;
- bases operacionais pendentes por cliente + regional;
- vínculos confirmados, alteração e desativação;
- resumo de sincronizados, PAI, FILHO, materializados, pendências e erros;
- filtros por texto, cliente, regional, OXXO e tipo de pendência;
- confirmação unitária e lote de alta confiança;
- ação separada para materializar eventos resolvidos.

Acesso exige permissão específica. `perfil.is_admin` sozinho não autoriza.

## 10. Interrupções e comandos

- `KeyboardInterrupt` fecha o run como `FAILED/INTERRUPTED` e relança a
  interrupção;
- `mark_stale_inventory_planning_runs --minutes 30` marca apenas runs anteriores
  ao limite e nunca libera execução recente;
- `list_inventory_planning_bindings` lista vínculos e pendências;
- `suggest_inventory_planning_bindings` calcula sugestões sem gravar;
- `materialize_inventory_planning --resolved-only` processa somente resolvidos.

## 11. Tory

A Tory continua em modo read-only:

```text
Tory → PlanningService → repository/models locais sincronizados
```

O escopo passará a considerar o par cliente + regional. Termos como `Campinas`
e `SP INT CPN` poderão abranger operações relacionadas; `OXXO Campinas` só será
associado à base X após bindings confirmados. Sem cliente suficiente para
desambiguar, Tory mostrará as operações encontradas ou pedirá o cliente, sem
declarar equivalência.

## 12. Impactos

Eventos já sincronizados não serão duplicados nem reimportados. Após confirmar
bindings, os mesmos `PlanningEvent` pendentes poderão ser materializados. O
binding evento → inventário existente continua sendo a chave idempotente.

Materializações futuras ganham resolução combinada e isolamento por evento;
uma inconsistência não interromperá o lote.

## 13. Plano de testes

Serão cobertos todos os cenários do pedido: cliente, sugestões não persistentes,
OXXO/regular, ambiguidade, precedência combinada, fallback simples,
idempotência, FILHO, campos locais preservados, cancelado/modificado, campos
ausentes, isolamento de erro, permissões, interrupção e stale run. Tory terá
testes para Campinas regular, OXXO Campinas e consulta ambígua sem cliente.

## 14. Arquivos previstos

Criar:

- `integracao/services/binding_suggestions.py`;
- `integracao/services/operational_base_resolver.py`;
- `integracao/views.py`, `integracao/urls.py`;
- `integracao/templates/integracao/planning_mappings.html`;
- quatro comandos de gestão;
- migration e testes específicos.

Alterar:

- `integracao/models.py`, `admin.py` e materializador;
- serviço de sincronização para interrupções;
- URLs, navegação e PlanningService/Tory;
- documentação operacional.

## 15. Riscos e rollback

Riscos principais: falso positivo OXX/OXO, regional com suboperações, vínculo
combinado incorreto confirmado em lote, alteração de base após execução e run
real marcado stale. As mitigações são confirmação explícita, score único,
permissões separadas, bloqueio de campos após execução e idade mínima.

Rollback: desativar novos bindings, interromper materialização, reverter código
e migration aditiva, mantendo eventos sincronizados e
`InventoryPlanningEventBinding`. Nenhum rollback deve excluir inventários ou
dados de execução. Antes de produção, validar manualmente um OXXO, um não OXXO,
uma regional ambígua, uma inequívoca, um PAI e um FILHO.
