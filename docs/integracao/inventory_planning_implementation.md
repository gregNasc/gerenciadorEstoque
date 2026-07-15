# Implementação da integração Inventory Planning

## Escopo entregue

A primeira fase sincroniza somente:

- `/regions`;
- `/clients`;
- `/stores`;
- `/inventory-types`;
- `/events`.

Os dados externos são persistidos no app `integracao` como projeção read-only.
Equipamentos, insumos, checklists, TAGs, movimentações, consumo, custos e tempos
reais continuam sob responsabilidade do `gerenciadorEstoque`.

## Configuração

Configure por ambiente:

```text
INVENTORY_PLANNING_API_URL=https://host/api/integration/v1
INVENTORY_PLANNING_API_KEY=ipk_...
INVENTORY_PLANNING_TIMEOUT=15
INVENTORY_PLANNING_MAX_RETRIES=4
INVENTORY_PLANNING_BACKOFF_BASE=1
INVENTORY_PLANNING_CATALOG_CACHE_TTL=21600
INVENTORY_PLANNING_SYSTEM_USERNAME=inventory_planning_sync
```

A aplicação recusa URL sem HTTPS. A API Key nunca deve ser colocada em arquivos
versionados, argumentos de linha de comando ou logs.

## Preparação do banco

```powershell
python manage.py migrate
```

As migrations criam somente tabelas e constraints do app `integracao`. Nenhum
inventário legado é alterado durante a migration.

## Primeira sincronização segura

Primeiro carregue a projeção sem materializar inventários:

```powershell
python manage.py sync_inventory_planning --no-materialize
```

Na tela **Estoque → Mapeamentos Planning**, configure:

1. `PlanningClientBinding`: cliente externo → `insumos.Cliente`;
2. `PlanningOperationalBaseBinding`: cliente externo + regional externa → base
   operacional local;
3. `PlanningRegionBinding` somente como fallback para regionais realmente
   inequívocas.

Os bindings são explícitos, possuem origem, responsável, timestamps e estado
ativo/inativo. Sugestões exibem confiança e motivo, mas não são gravadas sem
confirmação. O sistema não associa registros apenas pelo nome. Isso é essencial
para locais como Campinas, onde `SP INT CPN` e `OXXO SP INT CPN X` coexistem.

Depois materialize os eventos PAI:

```powershell
python manage.py materialize_inventory_planning --resolved-only
```

Eventos sem os dois bindings permanecem com status `PENDING` e um código de
pendência. Eles continuam sincronizados e podem ser materializados depois.

Comandos de apoio, todos sem acesso direto da Tory à API:

```powershell
python manage.py list_inventory_planning_bindings
python manage.py suggest_inventory_planning_bindings
python manage.py mark_stale_inventory_planning_runs --minutes 30
```

O comando de sugestões é somente leitura. Runs interrompidos recebem
`FAILED/INTERRUPTED`; apenas o comando explícito acima converte runs antigas em
`STALE`.

## Sincronizações seguintes

```powershell
python manage.py sync_inventory_planning
```

Opções disponíveis:

```text
--catalogs-only
--events-only
--no-materialize
```

Sugestão de agendamento:

- catálogos a cada 6 horas;
- eventos a cada 15 minutos;
- snapshot global noturno para reconciliação de ausências.

Uma sincronização parcial com filtros nunca marca registros fora da janela como
ausentes. Apenas um snapshot global concluído pode fazer essa reconciliação.

## PAI, FILHO e horários

- `inventoryType.type` e `parentEventId` são as fontes oficiais da hierarquia;
- todo PAI com bindings cria exatamente um `Inventario` local;
- eventos FILHO não criam `Inventario` nem checklist próprio;
- `plannedAt` é o início planejado oficial;
- o instante é armazenado com timezone e convertido para `America/Sao_Paulo` ao
  gerar `data_inicio` e `horario_inicio` locais;
- `importData.horarioInicio` não sobrescreve `plannedAt`;
- nenhum horário de término é presumido.

## Proteção dos dados locais

Ao atualizar um inventário vinculado, a integração escreve somente campos de
planejamento. Os seguintes dados locais não são alterados:

- status operacional já iniciado/finalizado;
- início e fim reais;
- início e fim da contagem;
- peças realizadas;
- custo por hora;
- checklist, equipamentos, insumos, TAGs, consumo, custos e históricos.

O formulário desabilita campos de planejamento oficiais. A importação XLSX não
sobrescreve nem remove inventários vinculados à API.

## Cancelados, removidos e ausentes

- `CANCELLED`, `MODIFIED`, `ADDED` e `REMOVED` são preservados no evento externo;
- nenhum desses estados exclui o `Inventario`, checklist ou histórico local;
- registros ausentes de snapshot completo recebem `sync_state=MISSING`;
- não há exclusão física durante sincronização.

## Dados sensíveis

O mapper remove campos de CPF, RG, PIS, PIX, contas bancárias, documentos,
telefone, celular, e-mail, data de nascimento e CNPJ MEI encontrados em
`importData`. Os valores removidos não são enviados aos logs.

Os endpoints de colaboradores, equipes, disponibilidade, conferentes avulsos e
composição de valor não fazem parte desta fase.

## Tory

A Tory nunca instancia o cliente HTTP. O fluxo de leitura é:

```text
Tory → PlanningAssistantService → PlanningService → models sincronizados
```

Perguntas sobre inventários futuros, pessoas e peças previstas, regional,
eventos PAI/FILHO e planejado × realizado usam o planejamento sincronizado. A
execução local só é cruzada quando existe `InventoryPlanningEventBinding` e o
inventário pertence ao escopo de acesso do usuário.

O contexto conversacional preserva período, evento externo, cliente, loja,
regional, tipo e status. As respostas indicam a fonte e a data do snapshot. Se
a última sincronização falhar, a Tory usa o snapshot existente; sem snapshot,
ela oferece as consultas locais sem interromper a conversa.

Consultas de disponibilidade, nomes de equipe, valores e avulsos não acessam os
endpoints futuros. A Tory pode explicar a limitação e calcular cenários
hipotéticos de quantidade, mas não altera a escala nem confirma disponibilidade.

A Tory também aceita o próprio nome como vocativo (`Tory, ...`, `Oi, Tory` ou
`Tory`). Quando uma cidade possui mais de uma operação, ela mostra as operações
permitidas e pede o cliente em vez de escolher uma base silenciosamente. Toda
consulta continua passando pelos serviços de domínio e pelo escopo de permissão;
nenhum dado pessoal, bancário ou financeiro é entregue diretamente pelo modelo
conversacional.

## Auditoria

Cada endpoint gera um `InventoryPlanningSyncRun` contendo:

- início e fim;
- status;
- páginas e registros recebidos;
- criados, atualizados e ausentes;
- inventários materializados e pendentes;
- `RateLimit-Limit`, `RateLimit-Remaining` e `RateLimit-Reset`;
- código de erro sanitizado.

Uma constraint impede duas sincronizações simultâneas do mesmo endpoint.

## Testes

```powershell
python manage.py test integracao.tests
```

A suíte cobre autenticação, HTTPS, paginação, timeout, retry, `Retry-After`,
401/403, idempotência, atualização, PAI/FILHO, cancelamento, campos opcionais,
relacionamentos de catálogo, sanitização, logs, rate limit, concorrência,
bindings combinados, OXXO/regular, permissões, interrupção/stale run e o vocativo
da Tory.
