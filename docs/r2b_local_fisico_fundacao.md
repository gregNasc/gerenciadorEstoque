# R2.B — Fundação de Local Físico

## Estado

Subetapa concluída localmente em 07/10/2026.

## Escopo entregue

- entidade `LocalFisico` pertencente a uma empresa;
- tipos Escritório, Base Logística, Depósito e Outro;
- endereço canônico e estado ativo;
- relação explícita entre Local Físico e Base;
- múltiplas Bases podem compartilhar o mesmo Local Físico;
- cada Base possui no máximo um Local Físico vigente nesta fundação;
- compartilhamento entre empresas exige relacionamento com capacidade
  `OPERACAO:ADMINISTRAR` ativa;
- policy tenant-aware considera a empresa proprietária e as Bases
  explicitamente vinculadas;
- ações desconhecidas falham fechadas.

## Compatibilidade

`EnderecoPostalBase` foi preservado integralmente. Declarações dos Correios
continuam usando o endereço postal legado, sem conversão automática e sem
alteração de dados existentes.

## Migration

`estoque.0064_localfisico_vinculobaselocalfisico_localfisico_bases_and_more`

A migration é aditiva e cria somente tabelas, constraints e índices novos.

## Limite desta subetapa

Ainda não foram criados:

- telas ou endpoints de Local Físico;
- conversão de `EnderecoPostalBase`;
- Custódia e seus itens;
- elegibilidade de ativos para Custódia;
- termos ou DocuSign.

## Validação

- testes direcionados R2.B: 6/6;
- R2.A/R2.B + Correios + regressões multi-tenant: 47/47;
- `python manage.py check`: aprovado durante a execução dos testes.

## STOP

Não houve commit, push, migration no banco local/produção ou deploy.
Não iniciar R2.C sem autorização.
