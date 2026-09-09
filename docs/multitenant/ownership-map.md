# Mapa de Ownership Multi-Tenant

## Status

- Etapa: 2 — Mapa de Ownership
- Estado: concluída
- Data: 2026-09-04
- Tenant conceitual: `estoque.Empresa`
- Models registrados analisados: 114
- Alterações de schema ou dados: nenhuma

## Convenções

- **Direto:** o model possui FK para `Empresa`.
- **Indireto:** a empresa é alcançada por uma cadeia de FKs obrigatória.
- **Múltiplo:** o registro participa de um fluxo com mais de uma empresa
  possível, como origem e destino.
- **Usuário:** hoje depende de `User → Perfil → Empresa`; essa rota é incompleta
  para Admin e Superuser no estado atual.
- **Global candidato:** o model parece representar catálogo ou configuração
  compartilhada, mas a decisão de negócio ainda precisa ser formalizada.
- **Global de plataforma:** o dado pode ser administrado globalmente, mas sua
  exposição operacional ainda exige policy.

O risco considera a clareza da rota de ownership, a sensibilidade do dado e a
possibilidade de relacionamentos contraditórios. Ele não afirma que já existe
vazamento.

## Resumo por app

| App | Models registrados | Situação principal |
|---|---:|---|
| estoque | 39 | Tenant, ativos, movimentações, mensagens e documentação |
| auditorias | 8 | Ownership herdado da campanha/base, com múltiplas rotas a validar |
| insumos | 27 | Catálogo global candidato e operação herdada de Base/Inventário |
| integracao | 10 | Espelho global do Planning e bindings para objetos locais |
| ordens_servico | 6 | Empresa direta na O.S.; filhos herdam a O.S. |
| compras | 11 | Empresa direta na aquisição/remessa; catálogo compartilhado |
| chamados | 13 | Empresa direta no chamado; filhos herdam o chamado |
| core | 0 | Nenhum model registrado |

O diretório `equipamentos/` não é um app Django instalado e contém somente
arquivos de imagem; os equipamentos persistidos pertencem a `estoque`.

## App `estoque`

| Model | Ownership | Tipo | Global legítimo? | Risco |
|---|---|---|---|---|
| Empresa | O próprio registro é o tenant | direto | somente administração da plataforma | baixo |
| Base | `empresa` | direto | não | baixo |
| EnderecoPostalBase | `base → empresa` | indireto | não | baixo |
| Perfil | `empresa`; escopos adicionais por empresas/bases | direto, atualmente opcional | não; Superuser é exceção conceitual | alto — Admin perde empresa no `save()` |
| AuditoriaPermissaoUsuario | `usuario → perfil → empresa`, quando existir | usuário | consolidação somente da plataforma | alto — Admin atual não possui empresa |
| GrupoRegional | conjunto reverso `bases → empresa` | indireto, não garantido | não | alto — schema permite bases de empresas distintas |
| Produto | sem empresa; catálogo de equipamentos | sem ownership | global candidato | médio — preço e fornecedor podem exigir escopo |
| Equipamento | `regional → empresa` | indireto | não | alto — ativo central e alvo de IDs manipuláveis |
| Emprestimo | `regional_origem` e `regional_destino` | múltiplo | não | alto — fluxo potencialmente cross-tenant |
| ItemEmprestimo | `emprestimo → origem/destino`; equipamento possui empresa própria | múltiplo indireto | não | alto — consistência entre fluxo e equipamento |
| Solicitacao | `regional_solicitante → empresa`; origem pode ser outra empresa | múltiplo | não | alto — solicitação e atendimento podem cruzar empresas |
| SolicitacaoItem | `solicitacao → regional_solicitante → empresa` | indireto | não | médio |
| AlocacaoSolicitacaoItem | solicitação, `regional_origem` e equipamentos | múltiplo indireto | não | alto — três rotas precisam concordar com a policy |
| AlocacaoEquipamento | alocação e equipamento | múltiplo indireto | não | alto — validar compatibilidade do equipamento |
| Transferencia | `regional_origem` e `regional_destino` | múltiplo | não | alto — cross-tenant deve ser capability explícita |
| TransferenciaItem | transferência e equipamento | múltiplo indireto | não | alto |
| DeclaracaoCorreios | transferência ou empréstimo | múltiplo indireto | não | alto — contém documento operacional |
| DeclaracaoCorreiosItem | declaração e equipamento | múltiplo indireto | não | alto |
| Notificacao | transferência, solicitação e destinatário | múltiplo/usuário | não | alto — combina objeto e usuário, ambos opcionais |
| PedidoTransferencia | solicitação, origem e destino | múltiplo | não | alto |
| PedidoItem | `pedido → solicitação/origem/destino` | indireto múltiplo | não | médio |
| TransferRequest | solicitação, origem e destino | múltiplo | não | alto — model legado paralelo a pedido/transferência |
| DivergenciaTransferencia | transferência, item e equipamento enviado | múltiplo indireto | não | alto |
| PendenciaTransferencia | transferência, item e equipamento | múltiplo indireto | não | alto |
| Sick | `equipamento → regional → empresa`; `base_origem` adicional | indireto com duas rotas | não | alto — bases precisam pertencer à mesma empresa autorizada |
| Historico | `equipamento → regional → empresa` | indireto | não | alto — auditoria sensível deve acompanhar o objeto |
| Descricao | sem relacionamentos | sem ownership | global candidato/legado | médio — confirmar finalidade antes de manter global |
| Alerta | sem relacionamentos | sem ownership | a definir | alto — model não oferece rota de isolamento |
| Comunicado | `empresa` opcional; destinatários e flag global | direto/usuário/global | sim, apenas quando explicitamente global | alto — `empresa=NULL` possui mais de um significado |
| ComunicadoEntrega | `comunicado`; destinatário | indireto/usuário | acompanha comunicado global | alto — dados de entrega e provedor são sensíveis |
| ComunicadoArquivo | `comunicado → empresa` | indireto | acompanha comunicado global | alto — arquivo precisa de autorização no download |
| ComunicadoLeitura | comunicado e usuário | indireto/usuário | acompanha comunicado global | médio |
| ComunicadoOculto | comunicado e usuário | indireto/usuário | acompanha comunicado global | médio |
| Mensagem | remetente; destinatários estão em model filho | usuário | não por padrão | alto — não existe empresa no registro |
| MensagemDestino | mensagem e destinatário | usuário/múltiplo | não por padrão | alto — conversa cross-tenant precisa ser explícita |
| MensagemArquivo | `mensagem → remetente/destinatários` | indireto/usuário | não | alto — arquivo privado sem tenant direto |
| VideoDocumentacao | sem empresa; autor opcional | catálogo global | sim, plataforma | baixo — conteúdo é referência compartilhada |
| ResolucaoDocumento | sem empresa; autor opcional | catálogo global | sim, plataforma | médio — arquivo exige policy de download |
| DriverImpressora | sem empresa; autor opcional | catálogo global | sim, plataforma | médio — binário exige policy de download |

## App `auditorias`

| Model | Ownership | Tipo | Global legítimo? | Risco |
|---|---|---|---|---|
| CampanhaAuditoria | `empresa` | direto | não | baixo |
| CampanhaAuditoriaEvento | `campanha → empresa` | indireto | não | médio — log sensível |
| AuditoriaBase | `campanha → empresa` e `base → empresa` | indireto com duas rotas | não | alto — falta garantir concordância |
| AuditoriaSnapshotEquipamento | auditoria/base, equipamento e base esperada | múltiplas rotas indiretas | não | alto — snapshot não pode misturar tenants |
| AuditoriaLeitura | auditoria/base, equipamento e base encontrada | múltiplas rotas indiretas | não | alto |
| AuditoriaDivergencia | auditoria, leitura, snapshot, equipamento e bases | múltiplas rotas indiretas | não | alto |
| AuditoriaResolucao | divergência, bases e transferência | múltiplas rotas indiretas | não | alto — pode criar movimentação cross-tenant |
| AuditoriaEvento | auditoria e divergência | indireto | não | alto — histórico deve seguir o escopo da auditoria |

## App `insumos`

| Model | Ownership | Tipo | Global legítimo? | Risco |
|---|---|---|---|---|
| CategoriaInsumo | sem empresa; taxonomia | catálogo global | sim, candidato | baixo |
| Insumo | sem empresa; categoria e preço | catálogo global | sim, candidato | médio — limites podem variar por tenant no futuro |
| FornecedorInsumo | sem empresa | catálogo global | sim, candidato | médio — contatos e condições podem ser tenant-specific |
| PrecoFornecedorInsumo | insumo e fornecedor globais; autor | catálogo global/usuário | a confirmar | alto — informação financeira |
| PesquisaPrecoOnline | insumo global e pesquisador | catálogo global/usuário | a confirmar | médio |
| OfertaPrecoOnline | pesquisa e insumo | catálogo global | a confirmar | médio |
| SolicitacaoInsumo | `base → empresa` | indireto | não | alto — aprovação e compra possuem usuários distintos |
| ItemSolicitacaoInsumo | `solicitacao → base → empresa` | indireto | não | médio |
| MovimentacaoInsumo | `base → empresa`; solicitação opcional | direto via Base | não | alto — impacto de saldo |
| SaldoInsumoBase | `base → empresa` | indireto | não | alto — saldo por tenant |
| HistoricoCadastroInsumo | `insumo` global e autor | catálogo global/usuário | acompanha catálogo | médio |
| Cliente | sem empresa; cliente operacional | sem ownership | global candidato | alto — usado por inventários de vários tenants |
| TipoRelatorioCliente | sem empresa; taxonomia | catálogo global | sim, candidato | baixo |
| ClienteRelatorio | cliente e tipo globais | catálogo global | a confirmar | médio |
| ClienteChecklistDocumento | cliente global e autor | catálogo global/usuário | a confirmar | alto — arquivo privado e potencialmente contratual |
| Inventario | `base → empresa` | indireto | não | alto — principal objeto operacional do módulo |
| AlteracaoCalendario | `base → empresa`; cliente global | indireto | não | alto |
| ChecklistDiario | `inventario → base → empresa` | indireto | não | alto |
| ItemChecklist | `checklist → inventario → base → empresa` | indireto | não | médio |
| ChecklistEquipamento | checklist e equipamento | duas rotas indiretas | não | alto — empresas precisam coincidir |
| ChecklistEquipamentoQuantidade | `checklist → inventario → base → empresa` | indireto | não | médio |
| ChecklistLoteTag | checklist, lote e rolo | múltiplas rotas indiretas | não | alto — inventário e lote devem compartilhar tenant/base |
| ConsumoInsumo | inventário e item de checklist | múltiplas rotas indiretas | não | alto |
| HistoricoInsumo | somente usuário, descrição e JSON | legado textual/usuário | preço pode ser global; operação não | alto — não possui FK para objeto operacional |
| LoteTag | `base → empresa` | indireto | não | alto — representa saldo/faixa física |
| RoloTag | `lote → base → empresa` | indireto | não | médio |
| MovimentacaoTag | inventário e lote | duas rotas indiretas | não | alto — rotas precisam pertencer ao mesmo tenant autorizado |

## App `integracao`

Os models `Planning*` são um espelho da fonte externa Inventory Planning. Ser
global na persistência não autoriza sua exposição global aos usuários. O tenant
operacional surge apenas quando há binding com Base/Inventário local.

| Model | Ownership | Tipo | Global legítimo? | Risco |
|---|---|---|---|---|
| PlanningRegion | fonte externa, sem tenant local | integração global | sim, plataforma | médio |
| PlanningClient | fonte externa, sem tenant local | integração global | sim, plataforma | alto — cliente pode ser associado a tenant |
| PlanningStore | cliente e região externos | integração global | sim, plataforma | alto — endereço e documento corporativo |
| PlanningInventoryType | fonte externa; taxonomia | integração global | sim, plataforma | baixo |
| PlanningEvent | store, client e region externos | integração global | sim, plataforma | alto — planejamento e métricas operacionais |
| PlanningClientBinding | cliente externo → `Cliente` local | configuração global | somente plataforma | alto — `Cliente` local não possui tenant |
| PlanningRegionBinding | região externa → `Base → Empresa` | indireto | somente plataforma para administrar | alto |
| PlanningOperationalBaseBinding | cliente/região externos → `Base → Empresa` | indireto | somente plataforma para administrar | alto |
| InventoryPlanningEventBinding | evento externo → `Inventario → Base → Empresa` | indireto | não | alto |
| InventoryPlanningSyncRun | log agregado da integração | integração global | sim, plataforma | alto — scope e erros não devem vazar |

## App `ordens_servico`

| Model | Ownership | Tipo | Global legítimo? | Risco |
|---|---|---|---|---|
| SequenciaOrdemServico | `empresa` | direto | não | baixo |
| OrdemServico | `empresa`; bases e fluxos vinculados adicionais | direto com múltiplas rotas | não | alto — todas as referências precisam ser compatíveis |
| OrdemServicoLinha | `ordem → empresa`; equipamento pode fornecer outra rota | indireto | não | alto |
| OrdemServicoAssinatura | `ordem → empresa`; usuário | indireto/usuário | não | alto — assinatura sensível |
| OrdemServicoEvento | `ordem → empresa`; usuário | indireto/usuário | não | médio |
| OrdemServicoAnexo | `ordem → empresa`; usuário | indireto/usuário | não | alto — arquivo privado |

## App `compras`

| Model | Ownership | Tipo | Global legítimo? | Risco |
|---|---|---|---|---|
| CodigoCatalogo | `empresa`; produto ou insumo global | direto | não | médio |
| Aquisicao | `empresa` | direto | não | alto — dado financeiro |
| ItemAquisicao | `aquisicao → empresa` | indireto | não | alto — preço e quantidade financeiros |
| VinculoEquipamentoAquisicao | item/aquisição e equipamento | duas rotas indiretas | não | alto — empresas precisam coincidir |
| HistoricoValorEquipamento | `equipamento → base → empresa` | indireto | não | alto — histórico financeiro |
| HistoricoPrecoProduto | produto e fornecedor globais; autor | catálogo global/usuário | a confirmar | alto — preço compartilhado atualmente |
| RemessaCompra | `empresa`, origem e destino | direto/múltiplo | não | alto — validar bases e cross-tenant |
| ItemRemessaCompra | remessa, aquisição e equipamento/insumo | múltiplas rotas indiretas | não | alto |
| RecebimentoRemessa | `remessa → empresa` | indireto | não | alto |
| LinhaRecebimentoRemessa | recebimento e item de remessa | múltiplas rotas indiretas | não | alto |
| EventoCompra | aquisição e/ou remessa; usuário | indireto opcional/usuário | não | alto — rotas opcionais precisam de invariant |

## App `chamados`

| Model | Ownership | Tipo | Global legítimo? | Risco |
|---|---|---|---|---|
| CategoriaChamado | sem empresa; taxonomia | catálogo global | sim, plataforma | baixo |
| SequenciaChamado | `empresa` | direto | não | baixo |
| AliasUsuario | `usuario → perfil → empresa`, quando existir | usuário | identidade pode ser administrada pela plataforma | alto — alias é globalmente único e Admin não possui empresa |
| PendenciaVinculoLider | `inventario → base → empresa` | indireto | não | alto |
| InventarioLiderHistorico | `inventario → base → empresa` | indireto/usuário | não | alto |
| Chamado | `empresa`; base, inventário, equipamento e SICK adicionais | direto com múltiplas rotas | não | alto — referências precisam concordar |
| ChamadoMensagem | `chamado → empresa` | indireto/usuário | não | alto — notas internas exigem capability própria |
| ChamadoAnexo | chamado e mensagem | indireto | não | alto — arquivo privado |
| ChamadoEvento | `chamado → empresa` | indireto/usuário | não | médio |
| ChamadoSessaoAtendimento | `chamado → empresa`; atendentes | indireto/usuário | não | alto |
| ChamadoTransferenciaAtendente | `chamado → empresa`; usuários | indireto/usuário | não | alto |
| ChamadoAvaliacao | chamado e sessão de atendimento | indireto | não | alto — as duas rotas devem concordar |
| ChamadoConexaoAtendente | `usuario → perfil → empresa`, quando existir | usuário/efêmero | não | alto — eventos WebSocket não possuem tenant persistido |

## Auditoria agregada dos dados legados

A análise foi somente leitura e não exibiu nomes de usuários, empresas, bases ou
conteúdo dos registros.

### `HistoricoInsumo`

Existem 2.326 registros:

- 1.314 registros de movimentação possuem `base_id`; os 29 IDs distintos ainda
  apontam para Bases existentes.
- 354 registros de checklist possuem `checklist` numérico; os 30 IDs distintos
  ainda apontam para Checklists existentes, permitindo chegar ao Inventário e à
  Empresa.
- 651 registros operacionais guardam somente a Base como texto. No snapshot
  atual, cada texto corresponde exatamente a uma Base e a uma Empresa; não há
  correspondência ausente ou múltipla.
- 7 registros são eventos de preço, pertencentes ao catálogo global candidato.
- 1.321 registros foram criados por usuários cujo Perfil atualmente não possui
  Empresa; o usuário, sozinho, não pode ser usado como ownership seguro.

Conclusão: o ownership dos 651 registros textuais é recuperável hoje para um
backfill validado, mas não é uma rota permanente. Renomear ou duplicar Bases
antes do backfill pode torná-los ambíguos. Nenhuma associação foi gravada nesta
etapa.

### Outros pontos

- `Alerta` e `Descricao` não possuem registros no banco validado.
- Não existem `Mensagem` ou `MensagemDestino` no banco validado.
- Nenhum `GrupoRegional` contém atualmente Bases de mais de uma Empresa, embora
  o schema permita essa situação.
- Há 6 Comunicados sem Empresa: 2 estão marcados para todos; os demais possuem
  destinatários/autor que permitem identificar empresas. Um deles alcança mais
  de uma empresa e deve ser tratado como comunicação cross-tenant explícita.
- Há 45 auditorias de permissão ligadas a usuários sem Empresa: 38 pertencem a
  Superuser e 7 a Admin comum.
- Há 1.406 registros de presença de Chamados ligados a usuários sem Empresa:
  1.398 de Superuser e 8 de Admin comum.

## Rotas críticas e invariants necessários

```text
Equipamento ──> Base ──> Empresa
Inventário  ──> Base ──> Empresa
Chamado     ──> Empresa
O.S.        ──> Empresa
Aquisição   ──> Empresa
```

Objetos com `empresa` direta e referências a Base/Equipamento/Inventário devem
validar que todas as rotas apontam para o mesmo tenant, salvo relacionamento
cross-tenant explicitamente autorizado.

```text
Transferência / Empréstimo / Remessa
        ├── Empresa da origem
        └── Empresa do destino
```

Esses fluxos não possuem ownership singular suficiente para autorização. A
policy deve separar, no mínimo, visualizar, criar, enviar, receber, aprovar,
editar e cancelar.

## Decisões que permanecem abertas

- Confirmar como globais ou tenant-specific: Produto, Categoria/Insumo,
  Fornecedor, preços, Cliente e documentação de Cliente.
- Definir se comunicação direta pode cruzar tenants e em quais capabilities.
- Definir ownership persistente para `HistoricoInsumo` antes de endurecer o
  isolamento do módulo.
- Associar Admins comuns a uma Empresa nas etapas previstas, sem inferência
  automática ambígua.
- Decidir o ciclo de vida de `ChamadoConexaoAtendente`: adicionar tenant,
  derivar de contexto autenticado imutável ou expirar dados legados.
- Garantir invariants entre `empresa` direta e objetos relacionados nos models
  de Chamados, O.S., Compras e Auditorias.

## Compatibilidade Inventory Brasil → LATAM/OXXO

O mapa não encontrou relacionamento persistido nem regra baseada nesses nomes.
Hoje a compatibilidade decorre do acesso global de qualquer role Admin. A futura
restrição de Admin exige criar primeiro o relacionamento explícito e direcionado
Inventory Brasil → Inventory LATAM/OXXO, conforme as capabilities identificadas
na matriz de acesso.

## Próxima etapa

Etapa 3 — Matriz de acesso atual.
