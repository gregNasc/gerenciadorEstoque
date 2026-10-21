# R3.G — Fechamento técnico e release gate de EPI

O R3.G fecha o módulo de EPI com catálogo CAEPI oficial local, consulta
operacional, exportação e controles de acesso, sem iniciar funcionalidades da R4.

## Status

**APROVADO TECNICAMENTE PARA DEPLOY CONTROLADO**, condicionado à autorização
explícita do usuário, ao backup e à execução das migrations no mesmo release.

## Escopo validado

- cadastro EPI isolado por Base;
- CA obrigatório e validade do CA independente da validade física;
- tamanho/variante e numeração específica de botas;
- lote opcional;
- alertas de validade;
- snapshot EPI transparente no Checklist;
- estoque com detalhes em modal;
- entrada de estoque EPI vinculada ao CA, tamanho/variante, lote e validades;
- entrada operacional com patrimônio individual e quantidade unitária;
- insumos reutilizáveis individualizados por patrimônio;
- patrimônio sem duplicidade entre equipamentos e insumos;
- importação CAEPI disponível apenas ao Superuser, com prévia, publicação
  atômica, histórico, hash e execução idempotente;
- consulta de CA feita exclusivamente no catálogo oficial publicado no banco
  local, sem dependência de API externa durante o cadastro;
- preenchimento automático de validade, situação, natureza, equipamento,
  marca, referência e norma disponíveis no arquivo oficial;
- situação do CA com indicador visual (válido em verde; vencido, cancelado ou
  suspenso em vermelho);
- tabela principal de estoque sem poluição visual por múltiplos CAs; detalhes
  completos permanecem no modal;
- o mesmo CA pode receber várias entradas e tamanhos na mesma Base; certificado,
  variante e lote compatíveis são reutilizados sem impedir novos movimentos;
- exportação Excel do EPI por Base, com filtros de validade (vencido, até seis
  meses, vigente e sem data) e de registro (ativo/inativo), sem preços ou custos;
- Admin e Gestor cadastram equipamentos e insumos somente nas Bases permitidas;
- `jose.barboza` pode cadastrar equipamentos/insumos e vincular linhas, mas
  permanece bloqueado de valores, custos, preços e operações financeiras;
- migrations incrementais e sem remoção destrutiva de dados.

## Migrations da R3

- `0039_separar_natureza_forma_controle`;
- `0040_dados_epi`;
- `0041_certificadoepi_epi_ca_numero_nao_vazio`;
- `0042_alter_loteepi_codigo_lote_and_more`;
- `0043_itemchecklist_metadados_epi_snapshot`;
- `0044_ativos_individualizados`;
- `0045_normalizar_botas_e_operacionais`;
- `0046_padronizar_nome_botas`;
- `0047_movimentacao_metadados_epi_patrimonio`.
- `0048_certificado_snapshot_caepi`.

Migrations de Integração:

- `0006_caepi_catalogo_local`;
- `0007_ampliar_numero_laudo_caepi`.
- `0008_caepi_progresso_recuperacao`.

A `0007` amplia `numero_laudo` para 255 caracteres e corrige o erro de upload
causado por valores oficiais maiores que `varchar(120)`.

A `0008` acrescenta progresso e última atualização, identifica importações
interrompidas e marca como interrompidos os processamentos antigos que ficaram
órfãos após reinício da instância.

## Correção de memória no Render

Em 20/10/2026, o Render encerrou duas vezes a instância Starter por ultrapassar
512 MB durante a importação. A causa era a retenção simultânea do upload, do
conteúdo descompactado/decodificado e de conjuntos completos de hashes.

O importador agora:

- calcula SHA-256 em blocos de 1 MB;
- descompacta CSV/GZIP/ZIP incrementalmente;
- mantém lotes de até 1.000 registros em memória;
- atualiza o progresso no banco a cada lote;
- calcula novos, ausentes e inalterados por consultas no banco;
- permite reprocessar o mesmo SHA quando a execução anterior falhou ou foi
  interrompida;
- preserva a versão publicada até a confirmação explícita da nova prévia.

O relatório oficial de 21.629.809 bytes foi revalidado em banco isolado:
123.927 linhas processadas, 123.817 registros únicos, zero rejeitados e prévia
concluída em aproximadamente 51 segundos. A repetição idêntica foi idempotente
e retornou em menos de quatro segundos.

As migrations são incrementais. A R3 não remove tabelas, saldos, movimentos ou
campos legados necessários para compatibilidade.

## Validação executada

Em 20/10/2026:

- arquivo oficial analisado: **123.927 linhas válidas**;
- catálogo preparado: **123.817 registros únicos**, com **110 duplicatas exatas
  ignoradas** e **zero linhas rejeitadas**;
- importação e publicação integrais validadas em banco isolado;
- conjunto ampliado de Insumos/CAEPI/ordens/vínculo móvel: **225 aprovados**;
- cenário regressivo do CA `32807`: mesmo tamanho em múltiplas entradas e
  tamanhos diferentes na mesma Base, aprovado;
- a suíte geral avançou sem falhas funcionais até bloquear no primeiro teste de
  `WebsocketCommunicator`; o mesmo bloqueio foi reproduzido isoladamente antes
  de qualquer asserção, por limitação do runtime Windows/sandbox;
- `python manage.py compilemessages -l es`: aprovado.
- `python manage.py check`: aprovado;
- `python manage.py makemigrations --check --dry-run`: nenhuma alteração;
- `git diff --check`: aprovado (somente avisos de LF/CRLF).

O banco utilizado pelos testes é separado do banco de produção.

## Riscos residuais

- o deploy do código sem `migrate` pode causar erro de coluna inexistente ao
  acessar os novos metadados da movimentação;
- o arquivo CAEPI informa a natureza (`Nacional`/`Importado`), não a data física
  de fabricação do lote; a data de fabricação permanece preenchimento manual;
- a validação integral local usa SQLite isolado porque o PostgreSQL local não
  está disponível; migrations e publicação devem ser confirmadas no PostgreSQL
  do ambiente durante o deploy controlado;
- os quatro testes de websocket devem ser executados no CI/Linux ou em ambiente
  Windows fora do sandbox antes da promoção definitiva; o bloqueio local não
  envolve código do R3.G;
- cada patrimônio operacional representa uma unidade física e, por isso, sua
  entrada deve ter quantidade igual a 1;
- lote e validades são opcionais, porém CA e tamanho/variante são obrigatórios
  para todos os EPIs;
- a migration de padronização transforma somente o nome legado `BOTAS` em
  `Botas`, sem alterar quantidades ou vínculos.

## Operação de deploy

Antes do deploy, criar um ponto de recuperação do PostgreSQL conforme o recurso
de backup disponível no provedor. Depois, publicar o código aprovado e executar:

```text
python manage.py migrate --noinput
python manage.py check
python manage.py showmigrations insumos integracao
```

Confirmar que `insumos.0039` até `0048` e `integracao.0006` até `0008` aparecem
aplicadas. Depois, como Superuser, publicar o arquivo oficial pela tela Base
CAEPI ou pelo comando:

```text
python manage.py importar_caepi /caminho/RelatorioCA.csv.gz --usuario admin --publicar
```

## Validação pós-deploy

1. autenticar como Admin de uma empresa de teste;
2. abrir a entrada de Insumos e selecionar uma Base da empresa;
3. selecionar um EPI e confirmar a exibição de CA, tamanho/variante, lote e
   validades;
4. confirmar que CA e tamanho/variante são obrigatórios e lote/validade são
   opcionais;
5. cadastrar uma Bota com numeração e conferir o saldo e o modal de detalhes;
6. cadastrar um item Operacional com patrimônio e quantidade 1;
7. confirmar que patrimônio repetido e quantidade maior que 1 são recusados;
8. conferir alertas de CA/validade e um Checklist que utilize EPI;
9. validar que outra empresa não enxerga os registros cadastrados;
10. verificar o indicador verde/vermelho ao consultar um CA;
11. confirmar que a tabela principal não lista os CAs em linha;
12. exportar vencidos/próximos e ativos/inativos pelo modal e confirmar que não
    existem colunas financeiras;
13. autenticar como `jose.barboza`, validar cadastro/vínculo e confirmar bloqueio
    de todas as telas de preços/custos;
14. verificar logs da aplicação para erros de migration, integridade ou acesso.

## Rollback e recuperação

Se houver falha antes de novas entradas em produção, reimplantar a versão
anterior do código e restaurar o ponto de recuperação somente se necessário.
Como as migrations são aditivas, o código anterior pode ignorar as novas
estruturas; não executar downgrade destrutivo das migrations em produção sem
auditoria dos registros criados após o deploy.

Se houver falha depois de novas entradas, preservar o banco, retirar o release
de tráfego e corrigir o código. Restaurar backup apagaria movimentos realizados
após o ponto de recuperação e, portanto, exige decisão operacional explícita.

O deploy, commit e push continuam dependendo de autorização explícita.

## Encerramento

A R3 termina funcional e implantável. Nenhuma implementação da R4 foi iniciada.
