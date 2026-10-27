# Release Gate R6 — Solicitações Unificadas

## Status

**R6 concluída em código e testes locais.** O avanço para R7 depende de revisão, commit/push, aplicação das migrations e deploy autorizados separadamente.

## Escopo entregue

- formulário único para Insumo, EPI, Equipamento e Novo item;
- solicitação livre sem criação automática ou alteração de estoque;
- escopo por empresa/Base e acompanhamento do próprio pedido para Gestor e Operador;
- recebimento e análise por Compras/Admin;
- aprovação ou reprovação auditável;
- bloqueio de aprovação enquanto houver Novo item sem resolução;
- vínculo de Novo item a catálogo existente;
- criação autorizada de insumo ou equipamento e retorno ao pedido, com vínculo automático ao tenant correto;
- pedido realizado, recebimento e atendimento;
- linha do tempo com evento, responsável, data, status anterior e status novo;
- anexo com download protegido pelo mesmo escopo da solicitação;
- adaptação da Ordem de Serviço para itens unificados;
- comunicação interna reaproveitada, sem envio externo nesta release.

## Migrations

1. `insumos/0050_r6_solicitacoes_unificadas_fundacao.py`
   - amplia os tipos de item;
   - adiciona anexo, especificação e justificativa por item;
   - cria a linha do tempo e reconstrói eventos legados;
   - preserva os pedidos existentes.
2. `insumos/0051_r6_fluxo_completo_e_resolucao_catalogo.py`
   - adiciona os estados do fluxo de Compras;
   - registra a resolução de Novo item;
   - impede duas referências de resolução simultâneas.
3. `integracao/0009_caepi_arquivo_fonte_assincrono.py`
   - guarda o arquivo-fonte da importação CAEPI para processamento retomável;
   - elimina a importação pesada da requisição de upload e divide a carga em lotes curtos.
4. `integracao/0010_caepi_cursor_arquivo_processamento.py`
   - cria uma fonte privada normalizada com cursor real em bytes;
   - evita reler desde o início as linhas já confirmadas;
   - preserva e reposiciona tentativas iniciadas antes da atualização.

Todas as mudanças de schema são aditivas. A migration de linha do tempo contém carga de dados legados e deve ser aplicada antes de liberar a nova interface.

## Validações executadas

- `manage.py check`: sem erros;
- `makemigrations --check --dry-run`: nenhuma alteração pendente;
- `git diff --check`: sem erro de whitespace;
- suíte completa de `insumos`: **121 testes aprovados**;
- conjunto integrado R6 + Compras + Ordens de Serviço + CAEPI: **27 testes aprovados**;
- suíte dirigida da importação CAEPI retomável: **11 testes aprovados**;
- teste específico de criação autorizada e vínculo ao pedido: **1 teste aprovado**.

Os testes foram executados em SQLite isolado porque o PostgreSQL local não estava disponível. Isso não substitui o smoke test pós-migration no PostgreSQL do ambiente de deploy.

## Riscos residuais

- a reconstrução da linha do tempo pode levar mais tempo proporcionalmente ao volume de solicitações legadas;
- arquivos de solicitação e CAEPI dependem de storage persistente no ambiente;
- a página da importação CAEPI precisa permanecer aberta enquanto aciona os lotes curtos; se houver falha de rede ou reciclagem do worker, o mesmo arquivo pode ser retomado sem novo upload;
- SMTP e WhatsApp não pertencem a este gate e permanecem fora do deploy da R6.

## Sequência de deploy controlado

1. gerar backup recuperável do PostgreSQL;
2. confirmar storage persistente e variáveis atuais, sem trocar senhas ou segredos;
3. publicar exatamente a revisão revisada da branch `main`;
4. executar `python manage.py migrate` uma única vez;
5. executar `python manage.py check`;
6. reiniciar o serviço web;
7. executar os testes rápidos abaixo.

## Smoke test pós-deploy

- Gestor e Operador criam pedido somente em Base autorizada;
- pedido aceita item de catálogo e Novo item sem modificar estoque;
- Admin/Compras recebe e inicia a análise;
- Novo item não resolvido bloqueia a aprovação;
- item criado por Compras fica restrito à empresa do pedido e é vinculado automaticamente;
- aprovação, pedido, recebimento e atendimento aparecem na linha do tempo;
- solicitante não acessa pedido de outro usuário ou tenant;
- anexo pode ser baixado somente por usuário autorizado;
- importação CAEPI retorna rapidamente como “Processando”, avança em lotes sem erro 524 e retoma uma tentativa pausada sem reenviar o arquivo;
- preços e dados financeiros continuam invisíveis para perfis sem autorização.

## Rollback

- em falha funcional antes de uso real, reimplantar a revisão anterior e manter as tabelas/colunas aditivas;
- não reverter migrations com dados sem backup e validação específica;
- desabilitar temporariamente os links da R6 se a aplicação anterior não reconhecer o novo fluxo;
- em falha da importação CAEPI, interromper novos uploads, preservar o registro e o arquivo-fonte e reprocessar após a correção;
- restaurar o backup somente em incidente de integridade confirmado.

## Decisão do gate

**Código pronto para revisão e deploy controlado da R6. STOP antes da R7.**

