# Análise de entrada — Adicional K de e-mail e WhatsApp

**Documento analisado:** `04.ADICIONAL_NOTIFICAÇÕES_EMAIL_WHATSAPP.md`  
**Data da análise:** 27/10/2026  
**Estado:** análise documental concluída; implementação não iniciada.

## Conclusão

O plano é compatível com o roadmap e deve permanecer subordinado à R7. A ordem `R6 → deploy e smoke test → autorização → K.0/R7.A` está correta. O adicional não deve ser implementado antes da validação manual da R6 em produção.

## Atualização factual após o fechamento local da R6

- branch: `main`;
- SHA-base antes das alterações locais: `b2db5b7943c02d6808960bf8590ba747644dcc10`;
- Gate R6 local concluído;
- 121 testes da aplicação `insumos` aprovados;
- 27 testes integrados de R6, Compras, Ordens de Serviço e CAEPI aprovados;
- teste específico de criação autorizada de insumo, catálogo do tenant e retorno à solicitação aprovado;
- `manage.py check` sem erros;
- nenhuma migration pendente;
- deploy e validação pós-deploy ainda não executados.

Assim, o item K.0 pode considerar o **gate local** comprovado, mas continua bloqueado para implementação até o deploy manual e o smoke test informado pelo usuário.

## Evidências confirmadas no código

1. `ComunicadoEntrega` já possui os canais `SISTEMA`, `EMAIL` e `WHATSAPP`, idempotency key única, estados, tentativas e índice de processamento. A hipótese de migration para apenas acrescentar o canal `EMAIL` deve ser descartada.
2. Configurações SMTP do Django já existem em `estoque_django/settings.py`; a Custódia já possui feature flag e processador próprio de e-mail.
3. WhatsApp já possui feature flag desligada por padrão, provedor Meta, consentimento/revogação, assinatura de webhook, templates, retry e proteção contra regressão de status.
4. O dispatcher atual cria entregas de sistema e WhatsApp, mas ainda não cria entregas genéricas de e-mail para Comunicados.
5. O badge `solicitacoes_pendentes` usa `estoque.models.Solicitacao`, depende de Transferências e de `perfil.role == 'admin'`, além de contar globalmente. Ele não representa o fluxo canônico `insumos.SolicitacaoInsumo` da R6 e confirma a necessidade da investigação K.1.
6. O context processor executa rotinas de manutenção com escrita (`notificar_manutencoes_previstas` e `excluir_expirados`) durante renderizações. Isso contraria a regra operacional do novo adicional e deve ser inventariado em K.0, sem correção misturada ao deploy da R6.

## Risco crítico antes de habilitar e-mail

O comando `processar_entregas_comunicados` aceita todos os valores de `ComunicadoEntrega.Canal`, inclusive `EMAIL`. Entretanto, `OutboxService.processar` seleciona sempre o provedor retornado pelo módulo de WhatsApp e constrói payload de template Meta independentemente do canal recebido.

Até existir roteamento explícito por canal:

- **não executar** `python manage.py processar_entregas_comunicados --canal EMAIL`;
- não criar entregas genéricas de e-mail como `PENDENTE` nessa outbox;
- K.3 deve introduzir um adaptador SMTP ou dispatcher por canal e testes que impeçam o uso acidental do provedor errado;
- a implantação deve manter as flags externas desligadas por padrão.

## Ajustes recomendados no documento antes da execução

1. No prompt final, substituir `ADICIONAL_GERAL_K_R7_PLANO_IMPLEMENTACAO.md` pelo nome real `04.ADICIONAL_NOTIFICAÇÕES_EMAIL_WHATSAPP.md`.
2. Atualizar o ponto de partida: a suíte e o teste específico de insumo já terminaram com sucesso; falta deploy e smoke test.
3. Em K.0, registrar explicitamente a escrita indevida no context processor como risco de desempenho e concorrência.
4. Em K.3, declarar que o enum/modelo de e-mail já existe e que a primeira tarefa é separar o processamento por canal, preferencialmente sem migration.
5. Adicionar teste obrigatório garantindo que `--canal EMAIL` nunca invoque `MetaWhatsAppProvider`.
6. Manter K.1 como patch separado da R6: a causa do badge está comprovada, mas a correção somente deve começar após autorização.

## Baseline adicional validado

Foram executados em banco SQLite isolado:

- `estoque.test_comunicacoes_whatsapp`;
- `estoque.test_notificacoes_custodia_r2l`.

Resultado: **17 testes aprovados**, sem falhas e sem alterações externas.

## Próximo passo permitido

1. usuário realiza deploy manual da R6;
2. usuário executa o smoke test descrito em `docs/release_gate_r6.md`;
3. usuário informa o resultado e autoriza expressamente K.0;
4. executar somente K.0, documental e diagnóstico;
5. emitir relatório no formato do adicional e parar.

**STOP — aguardando deploy manual, validação pós-deploy e autorização para K.0.**

