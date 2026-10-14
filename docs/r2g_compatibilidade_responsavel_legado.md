# R2.G — Compatibilidade com responsável legado

## Estado

Subetapa implementada localmente em 08/10/2026.

## Escopo entregue

- `Equipamento.responsavel` foi preservado;
- Custódia vigente espelha o nome do Colaborador no campo legado;
- telas e integrações antigas continuam recebendo o campo já existente;
- edição manual fica somente leitura enquanto houver Custódia vigente;
- finalização ou cancelamento limpa apenas o valor gerenciado pela Custódia;
- valor legado divergente/manual nunca é apagado automaticamente;
- equipamentos sem Custódia permanecem integralmente inalterados;
- resolvedor central prefere a Custódia vigente e usa o legado como fallback.

## Migration

Nenhuma. Não houve alteração de schema nem conversão automática dos dados
livres existentes.

## Estratégia de transição

Para ativos incluídos no novo fluxo, Custódia é a fonte de verdade e o campo
legado funciona como espelho de compatibilidade. Para ativos ainda não
adotados, `responsavel` continua funcionando como antes. Uma migração futura só
poderá ocorrer após auditoria dos valores livres existentes.

## Limite desta subetapa

- nenhum Colaborador foi inferido a partir de texto livre;
- nenhuma Custódia foi criada automaticamente;
- Linha Móvel mantém seu próprio responsável e não é alterada por este espelho;
- devolução, termos, DocuSign e notificações ainda não foram iniciados.

## Validação

- testes acumulados R2.E/R2.G: 15/15;
- regressão R2.A–R2.G + catálogo fail-closed + linhas móveis: 81/81;
- edição, finalidade e histórico de Equipamentos: 9/9;
- template de edição compilado com sucesso;
- catálogo espanhol compilado sem mensagens pendentes.

## STOP

Não houve commit, push, migration aplicada no banco local/produção ou deploy.
Não iniciar R2.H sem autorização.
