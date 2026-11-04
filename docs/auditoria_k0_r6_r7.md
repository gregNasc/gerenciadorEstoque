# K.0 — Auditoria de entrada R6 → R7

**Data:** 27/10/2026  
**Branch auditada:** `main`  
**SHA local e remoto:** `458261980306b4bf2d5c360f7e2d3cc8a226275f`  
**Árvore de trabalho no início:** limpa  
**Natureza desta etapa:** diagnóstico e documentação; nenhuma alteração funcional

## 1. Estado do gate R6

O gate local documentado em `docs/release_gate_r6.md` registra:

- fluxo unificado de solicitações concluído;
- criação, vinculação autorizada e isolamento de `NOVO_ITEM` para insumo e equipamento;
- histórico legível por evento;
- 27 testes integrados de R6, Compras, Ordens de Serviço e CAEPI aprovados;
- ausência de migrations pendentes na validação do gate.

Na auditoria atual:

- `python manage.py check`: aprovado, sem alertas;
- `/health/live/` em produção: HTTP 200, `{"status": "ok"}`;
- `/health/ready/` em produção: HTTP 200, `{"status": "ok"}`;
- `makemigrations --check --dry-run`: interrompido após espera anormal e sem saída; a espera ocorreu na conexão/verificação do banco, sem evidência de geração de migration;
- o SHA efetivamente implantado e o smoke test autenticado da R6 ainda não foram comprovados por uma resposta versionada do serviço.

Conclusão: o código e o gate local da R6 estão comprovados. A produção está viva e pronta, mas a autorização para iniciar patch funcional de K.1 depende de confirmar o SHA implantado ou executar um smoke test autenticado do fluxo R6.

## 2. Fluxo canônico encontrado

```text
Gestor/Operador
  → insumos.views.solicitacoes.criar_solicitacao
  → SolicitacaoService.criar_solicitacao
  → SolicitacaoInsumo + ItemSolicitacaoInsumo
  → EventoSolicitacaoInsumo(CRIADA)
  → ComunicadoService.solicitacao_insumo_criada
  → Comunicado + destinatários do ciclo de Compras
  → transaction.on_commit
  → ComunicacaoDispatcher.criar_entregas
  → entrega SISTEMA e, se habilitado/consentido, WHATSAPP

Admin/Compras
  → detalhe/decisão com InsumosTenantPolicy(APPROVE)
  → RECEBIDA_COMPRAS
  → EM_ANALISE
  → APROVADA ou REPROVADA
  → PEDIDO_REALIZADO
  → RECEBIDA
  → FINALIZADA
  → EventoSolicitacaoInsumo em cada transição
```

### Fonte oficial e isolamento

- `SolicitacaoInsumo` é o agregado canônico da R6.
- `ItemSolicitacaoInsumo` aceita `INSUMO`, `EPI`, `EQUIPAMENTO` e `NOVO_ITEM`.
- `EventoSolicitacaoInsumo` é a linha do tempo persistida.
- consultas e decisões passam por `InsumosTenantPolicy.requests`, com escopo de Base/tenant.
- `NOVO_ITEM` só pode ser aprovado depois de vinculado a um catálogo autorizado da empresa/Base.
- anexos usam o mesmo queryset de escopo antes do download.

## 3. Pontos de Compras já existentes

| Estrutura | Uso atual | Extensão adequada na R7 |
|---|---|---|
| `Aquisicao` e `ItemAquisicao` | compra, fornecedor, itens, valores e status | cotações/aprovação/NF-e sem criar domínio paralelo |
| `RemessaCompra` e itens | envio para Base, via matriz ou entre Bases | recebimento parcial e divergências |
| `RecebimentoRemessa` e linhas | idempotência e quantidades recebidas/avariadas/faltantes | conferência Pedido × NF-e × físico |
| `EventoCompra` | histórico de aquisição ou remessa | eventos de R7 e rastreabilidade |
| `ComprasAccessPolicy` | tenant, Base, catálogo e bloqueio financeiro | fonte de autorização para badges, links e destinatários |
| `ComunicadoService` | alertas internos já usados por Compras | reutilizar; não criar central paralela |

## 4. Badge: causa comprovada

O badge de `estoque/context_processors.py` não consulta a solicitação canônica da R6. Ele conta globalmente `estoque.models.Solicitacao` quando Transferências está habilitado e o perfil tem `role == 'admin'`.

Consequências:

- solicitações da R6 (`insumos.SolicitacaoInsumo`) não aparecem no contador;
- o contador legado não aplica `InsumosTenantPolicy` nem `ComprasAccessPolicy`;
- a regra depende de cargo e feature de Transferências, não de capacidade de Compras;
- há risco de contagem global e vazamento quantitativo entre tenants;
- o menu de Solicitações Unificadas existe, mas sem contador próprio canônico.

O menor patch de K.1 deve substituir somente a origem desse contador por um serviço/queryset acionável da R6. Não deve somar o contador legado ao novo nem alterar o badge de Comunicados.

## 5. Riscos de desempenho e concorrência

1. `notificacoes_context` executa `notificar_manutencoes_previstas()` e `excluir_expirados()` durante a renderização de qualquer página autenticada. Isso introduz escrita, varredura e possível concorrência no caminho crítico do Dashboard.
2. O contador legado executa consulta global e não reaproveita uma policy canônica.
3. A listagem R6 limita resultados a 200, mas prefetcha itens e toda a linha do tempo; a paginação deverá ser avaliada na R7 se o volume crescer.
4. `usuarios_ciclo_compras` resolve Compras/Financeiro por empresa e Admins por policy. Antes de canais externos, deve ficar explícito se usuários funcionais de Compras atuam por empresa inteira ou também por Base/Regional.
5. Chamadas de comunicação da R6 criam o `Comunicado` dentro da mesma transação de domínio e criam entregas em `on_commit`, o que evita aviso de uma transação revertida. Entretanto, ainda não há um evento durável separado para reconciliar falha do callback após o commit.

## 6. Infraestrutura de comunicação existente

| Componente | Estado encontrado | Observação |
|---|---|---|
| `ComunicadoEntrega.Canal` | `SISTEMA`, `EMAIL`, `WHATSAPP` | schema já comporta e-mail; K.3 tende a exigir zero migration |
| unicidade | comunicado + usuário + canal | impede duplicidade básica de entrega |
| idempotência | UUID único por entrega | disponível para provedor externo |
| dispatcher | cria Sistema e WhatsApp | não cria entrega de e-mail |
| WhatsApp | feature flag, consentimento, escopo e retry | permanece desligado até homologação autorizada |
| processador | aceita `--canal EMAIL` | hoje encaminha qualquer canal ao provedor/payload de WhatsApp; não usar para e-mail |
| SMTP | não integrado ao dispatcher/outbox | implementar apenas em K.3, com flag desligada |

## 7. Matriz inicial de eventos e destinatários

| Evento de domínio | Destinatário mínimo | Conteúdo | Classificação |
|---|---|---|---|
| Solicitação criada | Compras autorizado no tenant + solicitante | protocolo, Base, prioridade e itens; sem preços | R6 existente / K.1 badge |
| Recebida por Compras | solicitante e responsáveis acionáveis | estado e link autorizado | K.2 junto da R7 |
| Em análise | solicitante | estado e link autorizado | K.2 junto da R7 |
| Aprovada/Reprovada | solicitante + ciclo autorizado | estado e observação sem preço por padrão | R6 existente; revisar em K.2 |
| Pedido realizado | solicitante + ciclo autorizado | estado e referência interna | R6 existente; integrar à aquisição na R7 |
| Cotação pendente | aprovadores autorizados | sem valores para José Barboza | R7/K.2 |
| Aquisição aprovada | Compras/Financeiro autorizados | versão financeira somente para capability financeira | R7/K.2 |
| Recebimento divergente | Compras e responsáveis da Base | divergência operacional; preço apenas quando autorizado | R7/K.2 |
| Recebimento concluído | solicitante, Compras e Base no escopo | resumo operacional | R7/K.2 |
| E-mail SMTP | mesmos destinatários já autorizados no processamento | payload mínimo | K.3 |
| WhatsApp | destinatário autorizado e com consentimento vigente | template homologado e payload mínimo | K.4 |
| Integração TOTVS | nenhum evento nesta release | fora de escopo | R9 |

## 8. Proteção financeira

`ComprasAccessPolicy.restrito()` identifica `jose.barboza` e o grupo restrito. A policy bloqueia visualização e edição/importação de preços, preservando cadastro operacional. K.1 e K.2 devem reutilizar essa policy no backend e gerar payload sem valores por padrão; nenhum e-mail, WhatsApp, anexo, XML, PDF, histórico ou URL pode contornar o bloqueio.

## 9. Arquivos mínimos previstos para K.1

- `estoque/context_processors.py` — remover escrita do caminho de renderização em etapa própria e trocar o contador legado pelo serviço canônico;
- `insumos/services/solicitacao_service.py` ou serviço de consulta específico — definir pendências acionáveis sem misturar transição com consulta;
- `insumos/policies.py` e/ou `estoque/policies/compras.py` — reutilizar escopo/capabilities, sem regra paralela por username/cargo;
- `estoque/templates/estoque/base.html` — somente se o badge precisar ser movido para o item correto;
- testes dirigidos de tenant, Base, perfil, deduplicação, encerramento e quantidade de queries.

Não há justificativa, nesta auditoria, para criar model, migration, app ou central de notificações adicional.

## 10. Critérios de eficiência e clareza para K.1

- uma fonte de contagem, sem soma legado + R6;
- queryset filtrado no banco, sem loop por solicitação;
- nenhuma escrita ou integração externa no context processor;
- contador representa tarefas que o usuário realmente pode executar;
- texto simples na interface: “Solicitações pendentes”, com link direto para a lista filtrada;
- estado vazio sem jargão técnico;
- teste de limite de queries para impedir regressão no menu global.

## 11. Resultado K.0

**Auditoria técnica:** concluída.  
**Alterações funcionais:** nenhuma.  
**Migrations:** nenhuma.  
**Próxima subetapa proposta:** K.1, iniciada por testes de reprodução do badge e de isolamento antes do patch.  
**Condição de avanço:** cumprida em 27/10/2026. O usuário confirmou o deploy
Render `dep-dbgcaf8m7kps73c19050`, Live, no SHA `4582619`.

