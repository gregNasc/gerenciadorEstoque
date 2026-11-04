# R7.D.1 — Documentos fiscais privados

## Objetivo

Proteger DANFE e XML de NF-e contra acesso público, vazamento entre empresas e envio de arquivos inválidos, preservando a leitura dos documentos legados já armazenados.

## Entregas

- armazenamento privado para novos DANFEs e XMLs, sem URL pública;
- nomes físicos opacos e separados por empresa;
- compatibilidade de leitura com documentos legados no armazenamento anterior;
- validação de extensão, tamanho e assinatura de PDF;
- validação estrutural do XML, com bloqueio de `DOCTYPE` e entidades externas;
- download autenticado, com escopo por empresa e permissão específica;
- bloqueio explícito para perfis restritos, inclusive `jose.barboza`;
- botões de download exibidos somente para quem pode acessar os documentos;
- permissão `compras.exportar_documentos_aquisicao` para concessões controladas;
- cabeçalhos de download seguro (`attachment` e `nosniff`).

## Banco de dados

A migração `compras.0008_alter_aquisicao_options_and_more` registra os validadores, caminhos privados e a nova permissão. Ela não remove nem transforma registros existentes.

## Validação executada

- 4 testes específicos de documentos fiscais privados;
- 64 testes do módulo Compras;
- 9 testes integrados de isolamento e terminologia;
- `manage.py check` sem erros;
- `makemigrations --check --dry-run` sem alterações pendentes.

## Implantação

Antes de publicar a aplicação, executar `python manage.py migrate`. No estado atual da branch, esse comando aplicará também as migrações de Compras ainda não instaladas no ambiente de produção.
