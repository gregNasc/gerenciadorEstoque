# Adicional H — Manutenção pelo Painel Superuser

## Status

Concluído.

## Acesso posterior à configuração

Cada empresa exibida no Painel Superuser agora possui a ação `Configurar tenant`, disponível nos layouts desktop e mobile.

A ação abre o mesmo fluxo seguro de dez etapas utilizado na criação, em modo de manutenção, permitindo alterar posteriormente:

- dados básicos;
- módulos e nomes de apresentação;
- terminologia;
- categorias;
- catálogo próprio e compartilhamentos explícitos;
- seções de documentação;
- primeiro Admin;
- bases;
- relacionamentos e suporte;
- revisão final.

## Comportamento de empresas ativas

- Uma empresa ativa não é mais expulsa do fluxo de configuração.
- O cabeçalho identifica claramente o modo `Manutenção do tenant`.
- O tenant permanece ativo enquanto as etapas são editadas.
- A etapa final conclui uma revisão, sem executar uma segunda ativação.
- Encerrar a manutenção preserva todas as alterações já salvas e mantém o status ativo.
- A ativação continua sujeita às validações obrigatórias da G.7.

## Preservação de dados

Desabilitar módulos, seções ou vínculos de catálogo não exclui os registros associados. Desativar e reativar uma empresa preserva:

- módulos e terminologia;
- categorias;
- produtos e vínculos de catálogo;
- documentação;
- usuários e bases;
- relacionamentos;
- histórico operacional.

Empresas inativas continuam disponíveis para configuração e reativação no painel, mas não recebem a ação operacional `Abrir tenant` e não aparecem nos seletores de empresas.

## Segurança

- O fluxo permanece exclusivo do Superuser.
- A empresa editada é resolvida pelo backend e mantida na sessão do onboarding.
- As validações tenant-specific das etapas G.1 a G.7 continuam sendo aplicadas.
- Nenhuma senha existente ou `SECRET_KEY` foi alterada.

## Validação

- `manage.py check`: aprovado.
- Testes focados de onboarding e manutenção: 23 aprovados.
- Suíte relacionada: 59 testes aprovados.
- Suíte completa: 617 testes aprovados em 1195,339 segundos, sem falhas ou erros.

## Próximo incremento

Adicional I — auditoria global de vazamentos, fallbacks e referências históricas.
