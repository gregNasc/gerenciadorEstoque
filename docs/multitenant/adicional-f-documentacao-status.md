# Adicional F — Documentação tenant-specific (24/09/2026)

O módulo de documentação passou a operar com configuração explícita por empresa.
Uma empresa sem `SecaoDocumentacaoEmpresa` habilitada não recebe menu, catálogo,
rota, upload ou download de documentação.

## Implementação

- menu e atalhos exibem somente seções habilitadas e seus nomes personalizados;
- middleware bloqueia GET, POST e downloads de seções desabilitadas;
- `DocumentationAccessPolicy` deixou de liberar registros com `empresa=NULL`
  automaticamente;
- o acesso ao acervo global legado depende do campo explícito
  `permite_conteudo_global_legado` em cada seção;
- a migration `0058_secao_documentacao_legado_explicito` preserva essa permissão
  apenas para as configurações existentes de Inventory Brasil, Inventory Latam e
  OXXO;
- manuais e JSONs legados são filtrados pelo tenant também em Tory e na tela de
  chamados;
- PDFs legados são entregues por endpoint autenticado, com `private, no-store` e
  `nosniff`;
- URLs diretas de `/static/manuais/` e `/static/documentacao/` são bloqueadas
  antes do WhiteNoise;
- desabilitar uma seção não remove seus documentos.

## Validação

- `python manage.py check`: aprovado;
- `python manage.py makemigrations --check --dry-run`: sem alterações;
- migration `0058` aplicada no banco local;
- 62 testes diretamente afetados: aprovados;
- suíte completa: 601 testes aprovados.

## Resultado de segurança

- tenant externo sem configuração: zero documentação herdada;
- tenant A não lista nem baixa documento do tenant B;
- acervo histórico só aparece quando a seção permite legado explicitamente;
- Grupo Inventory continua compatível por dados persistidos, sem regra de
  autorização baseada no nome da empresa em tempo de execução.
