# Etapa 23 — Painel exclusivo do Superuser

## Estado: concluída

O painel da plataforma consolida a operação administrativa multi-tenant em uma
visão exclusiva para `user.is_superuser`. Admins de empresa continuam sem
acesso à página, às ações POST e aos dados dos demais tenants.

## Visão da plataforma

O resumo apresenta:

- total de empresas e quantidade ativa;
- bases operacionais;
- usuários não-Superuser;
- relacionamentos ativos entre empresas.

Cada empresa exibe:

- status ativo/inativo;
- quantidade e lista resumida de módulos habilitados;
- primeiro Admin de tenant por data de criação;
- usuários ativos e totais vinculados à empresa;
- quantidade e nomes das bases;
- relacionamentos ativos de entrada e saída;
- atalho direto para abrir o tenant.

Empresas sem Admin são identificadas como pendentes. A criação guiada do
primeiro Admin faz parte do onboarding da Etapa 24 e não foi antecipada.

## Ações administrativas

O Superuser pode:

- ativar ou desativar uma empresa por POST com CSRF e confirmação visual;
- configurar os módulos de uma empresa em modal próprio;
- cadastrar empresa e base pelos recursos que já existiam no painel;
- abrir o tenant diretamente;
- acessar o cadastro técnico de relacionamentos e capabilities.

A configuração de módulos valida todo o payload antes de gravar, é executada
em transação atômica e usa `TenantFeatureService.configure`. Cada alteração
registra o Superuser responsável em `ModuloEmpresa.configurado_por`. Um código
de módulo desconhecido cancela a operação inteira.

## Relacionamentos

Uma seção dedicada lista origem, destino, status, compartilhamento de suporte
e número de capabilities ativas. Inclusão e edição usam as telas técnicas já
protegidas do Django Admin, com links diretos a partir do painel.

## Segurança

- usuário anônimo é redirecionado para autenticação;
- Admin de tenant recebe HTTP 403;
- a validação de Superuser ocorre antes de qualquer ação ou consulta global;
- ações de status e módulos aceitam somente empresas e valores válidos;
- a interface usa POST e CSRF para alterações;
- nenhuma senha é exibida, redefinida ou modificada;
- a etapa não cria nem promove usuários no banco de desenvolvimento.

## Migration

Não há mudança de schema nesta etapa e nenhuma migration foi criada.

## Validação

- 7 testes específicos do painel aprovados;
- regressão integrada das Etapas 21–23, painel anterior e isolamento de
  cadastro de usuários: 42 testes aprovados;
- `manage.py check`: sem problemas;
- `makemigrations --check --dry-run`: nenhuma alteração pendente;
- `git diff --check`: nenhuma inconsistência de whitespace.

Auditoria somente leitura do banco de desenvolvimento:

- 4 empresas, todas ativas;
- 11 módulos e 44 configurações empresa/módulo;
- 3 módulos já desabilitados em `ATROPIC` (`insumos`, `checklist` e `tory`),
  registrados como configurados por `admin` e preservados sem alteração;
- 2 relacionamentos cadastrados;
- somente `admin` é Superuser.

## Limite da etapa

O fluxo guiado “Nova Empresa”, com dados básicos, escolha inicial de módulos,
primeiro Admin, bases, relacionamentos e ativação final, pertence à Etapa 24.
Este painel fornece a visão operacional e os controles administrativos sem
antecipar esse onboarding.
