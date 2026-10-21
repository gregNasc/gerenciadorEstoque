# R4.A — Capacidades configuráveis dos ativos

## Estado

Fundação implementada e validada. Este incremento não altera automaticamente
os identificadores dos equipamentos existentes.

## Entregue

- reutilização de `CapacidadeCatalogoProdutoEmpresa`, sem novo modelo paralelo;
- capacidades tenant-aware para individualização, patrimônio, série, SICK,
  manutenção, transferência e inativação;
- configuração no Catálogo da empresa;
- validação de coerência: uma exigência não pode ser ativada quando o respectivo
  identificador não é permitido;
- compatibilidade legada: na ausência de configuração explícita, produtos já
  existentes mantêm patrimônio e série obrigatórios e os fluxos operacionais
  atuais;
- configuração explícita por empresa prevalece sobre o padrão legado;
- capacidades de chip/linha móvel e Custódia continuam preservadas.

## Próximo incremento

R4.B aplicará as capacidades de patrimônio e série ao cadastro e à edição de
equipamentos. Isso exige migration aditiva para permitir valores vazios no
banco sem remover a unicidade dos identificadores preenchidos, além de ajustes
nos templates e testes de compatibilidade.

## Validação

- 5 testes específicos de R4.A aprovados;
- 29 testes combinados de capacidades, Custódia e linhas móveis aprovados;
- `python manage.py check` aprovado;
- `python manage.py makemigrations --check --dry-run` sem alterações;
- `git diff --check` aprovado, somente com avisos locais de LF/CRLF.

Nenhum deploy, push ou alteração de dados de produção foi realizado.
