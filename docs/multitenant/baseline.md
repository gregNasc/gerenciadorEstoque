# Baseline multi-tenant

## Status

- Etapa: 1 — Baseline de funcionamento
- Estado: concluída
- Data: 2026-09-04
- Branch: `main`
- Commit de referência: `305266ab61e94d52959bba875962c4599772e567`
- Escopo desta etapa: diagnóstico e documentação; nenhuma regra de tenant, model ou dado foi alterado.

## Ambiente validado

- Python: 3.12.10
- Django: 5.2.17, conforme `requirements.txt`
- Banco configurado: PostgreSQL
- Banco de testes reutilizado: `test_estoque_render_dump`

O launcher `.venv\Scripts\python.exe` está quebrado e retorna `Unable to create
process`, pois aponta para uma instalação de Python que não é iniciada por ele.
Para o baseline foi usado o Python 3.12 instalado, com
`.venv\Lib\site-packages` no `PYTHONPATH`.

## Aplicações ativas

Aplicações de infraestrutura Django:

- `daphne`
- `django.contrib.admin`
- `django.contrib.auth`
- `django.contrib.contenttypes`
- `django.contrib.sessions`
- `django.contrib.messages`
- `django.contrib.staticfiles`

Aplicações do projeto:

- `estoque.apps.EstoqueConfig`
- `auditorias.apps.AuditoriasConfig`
- `core`
- `insumos`
- `integracao.apps.IntegracaoConfig`
- `ordens_servico.apps.OrdensServicoConfig`
- `compras.apps.ComprasConfig`
- `chamados.apps.ChamadosConfig`

## Middleware ativo

Na ordem de execução configurada:

1. `django.middleware.security.SecurityMiddleware`
2. `whitenoise.middleware.WhiteNoiseMiddleware`
3. `django.contrib.sessions.middleware.SessionMiddleware`
4. `django.middleware.locale.LocaleMiddleware`
5. `django.contrib.auth.middleware.AuthenticationMiddleware`
6. `estoque.middleware.UserLanguageMiddleware`
7. `estoque.middleware.EmpresaMiddleware`
8. `estoque.middleware.OperatorScopeMiddleware`
9. `django.middleware.common.CommonMiddleware`
10. `django.middleware.csrf.CsrfViewMiddleware`
11. `django.contrib.messages.middleware.MessageMiddleware`
12. `django.middleware.clickjacking.XFrameOptionsMiddleware`

### Middleware relevante ao escopo

- `EmpresaMiddleware` inicializa `request.empresa` com
  `request.user.perfil.empresa`. Erros de banco ou ausência de perfil resultam em
  `None`. Não existe ainda `request.tenant` nem um escopo central de empresas.
- `OperatorScopeMiddleware` restringe operadores a um conjunto de rotas e
  permite exceções por permissão Django, grupo funcional e alguns usernames.
  Superusers não passam por essa restrição de rotas.
- `UserLanguageMiddleware` ativa o idioma salvo no perfil.

## Autenticação atual

- O projeto utiliza `django.contrib.auth.models.User`; não há
  `AUTH_USER_MODEL` customizado.
- Não há `AUTHENTICATION_BACKENDS` explícito; vale o backend padrão do Django,
  `ModelBackend`.
- Login, logout e sessão usam a autenticação do Django.
- URLs configuradas:
  - login: `estoque:login`
  - redirecionamento após login: `estoque:index`
  - redirecionamento após logout: `estoque:login`
- A view de login chama `authenticate()` e `login()` e garante a existência de
  um `Perfil`, com role padrão `operador`.
- O signal de criação de `User` também cria um `Perfil` com role `operador`.
- Autorização é distribuída entre roles do `Perfil`, grupos, permissões Django,
  decorators, middleware, services e filtros de QuerySet.

## Comportamento atual dos perfis

### Superuser

- `user.is_superuser` ignora a restrição de rotas do
  `OperatorScopeMiddleware`.
- A criação de qualquer `User`, inclusive superuser, cria por padrão um
  `Perfil` operador sem empresa.
- Não há ainda uma política central que transforme `is_superuser` em escopo
  global de dados. Vários filtros verificam `perfil.is_admin`, e não
  `user.is_superuser`. Portanto, o comportamento global do Superuser é
  inconsistente entre módulos.

### Admin

- `Admin` é atualmente o role `Perfil.Role.ADMIN`, não uma condição baseada em
  `user.is_superuser`.
- `Perfil.save()` força `empresa = None` e limpa `regionais` para Admin.
- `Perfil.pode_ver_tudo` retorna verdadeiro para Admin.
- `secure_queryset()` retorna o QuerySet sem filtro de empresa ou base para
  Admin, ressalvadas regras específicas, como ocultação durante auditoria.
- A Tory retorna todas as bases, transferências e empréstimos para Admin em
  seus caminhos atuais.
- Qualquer usuário com role Admin pode cadastrar usuários, mesmo sem
  `is_staff` e sem `is_superuser`; esse comportamento possui teste automatizado.
- Não foi encontrada regra em Python baseada nos nomes `Inventory Brasil`,
  `Inventory LATAM` ou `OXXO`.
- A visibilidade atual de um Admin da Inventory Brasil sobre LATAM e OXXO é
  consequência do acesso global concedido a todo Admin. Ela ainda não é um
  relacionamento explícito, direcionado ou limitado por capability.

### Gestor

- É identificado por `Perfil.Role.GESTOR`.
- No helper central `secure_queryset()`, precisa possuir empresa e ao menos uma
  base em `regionais`; o QuerySet é filtrado pela empresa e pelas bases.
- As propriedades do perfil permitem transferir, receber e marcar SICK, mas não
  aprovam automaticamente.
- Views e módulos podem adicionar restrições por grupos e permissões Django.

### Operador

- É identificado por `Perfil.Role.OPERADOR` e é o role padrão de novos usuários.
- No helper `secure_queryset()`, precisa possuir empresa e bases vinculadas; sem
  bases, recebe QuerySet vazio.
- O middleware redireciona o dashboard principal para Chamados e bloqueia, por
  padrão, telas fora de manuais, chamados, comunicados e rotas explicitamente
  permitidas.
- Permissões Django e grupos funcionais podem liberar checklist, SICK, suporte,
  dashboard de chamados e outras rotas específicas.

### Perfis funcionais

- Os grupos de Compras, Planejamento, Financeiro e Executivo de insumos tornam
  `Perfil.is_funcional_global` verdadeiro.
- Esses perfis escapam da restrição de rotas aplicada a operadores.
- `Perfil.pode_ver_empresas_globais` retorna verdadeiro para Admin ou perfil
  funcional global. Esse comportamento deve ser mapeado antes de qualquer
  endurecimento multi-tenant.

## Proteções de dados já existentes

- `secure_queryset()` nega acesso quando não há perfil, filtra Gestor e Operador
  por empresa e bases e devolve QuerySet vazio quando o escopo necessário não
  existe.
- `validar_empresa_objeto()` valida alguns objetos que expõem `regional` ou
  `equipamento`, mas não constitui uma policy geral de tenant.
- A Tory possui filtros de bases e testes que impedem Gestor de obter
  equipamentos, inventários ou nomes de bases fora de seu escopo.
- Existem regras específicas adicionais nos services de SICK, Chamados,
  documentação, insumos e integrações. O comportamento ainda não está
  centralizado.

## Migrations

- `python manage.py makemigrations --check --dry-run`: nenhuma mudança detectada.
- `python manage.py showmigrations --plan`: todas as migrations listadas estão
  aplicadas.
- A migration `chamados/0011_tipo_chamado_e_base_opcional.py` está aplicada no
  banco local, mas o arquivo ainda não está rastreado pelo Git. Trata-se de uma
  alteração preexistente nesta etapa.
- Nenhuma migration foi criada ou executada como parte da Etapa 1.

## Testes executados

Comandos funcionais equivalentes aos exigidos pelo plano foram executados com o
Python 3.12 instalado e os pacotes da `.venv`:

```text
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py showmigrations --plan
python manage.py test estoque.test_user_access_profiles estoque.tests.ToryIsolamentoBasesTests --keepdb
```

Resultados:

- system check: OK, zero issues
- alterações de model sem migration: nenhuma
- migrations pendentes no banco validado: nenhuma
- testes focados: 12 executados, 12 aprovados
- suíte completa: não executada nesta etapa

A primeira tentativa de testes, sem `--keepdb`, encontrou o banco de teste já
existente e abortou ao solicitar confirmação interativa. Nenhum banco foi
apagado. A repetição não destrutiva com `--keepdb` foi aprovada.

## Bloqueio de segurança encontrado e tratado

Foi encontrado um fallback de senha PostgreSQL versionado em
`estoque_django/settings.py` e repetido em `.env.example`. Conforme a regra de
STOP do plano, a etapa foi interrompida até autorização explícita.

Após autorização:

- a senha do banco não foi alterada;
- o mesmo valor foi armazenado como `POSTGRES_PASSWORD` no ambiente do usuário
  Windows;
- o mesmo valor foi salvo no arquivo local `.env`, ignorado pelo Git, para que
  terminais já abertos e o servidor de desenvolvimento também o carreguem;
- o fallback foi removido de `settings.py`;
- o exemplo passou a deixar o valor em branco;
- a inicialização agora falha de forma explícita quando o desenvolvimento local
  não fornece `POSTGRES_PASSWORD` e não utiliza `DATABASE_URL`;
- a busca no workspace não encontrou mais o valor hard-coded fora de `.git`.

O settings carrega `.env` sem sobrescrever variáveis já fornecidas pelo ambiente.
A credencial pode continuar no histórico Git; ela não foi rotacionada por
instrução expressa do responsável.

## Estado preexistente do working tree

Antes desta etapa já havia alterações não commitadas em arquivos de `chamados`,
no template `estoque/templates/estoque/checklist.html` e na migration não
rastreada `chamados/migrations/0011_tipo_chamado_e_base_opcional.py`.

Essas alterações foram preservadas e não foram modificadas nesta etapa.

## Riscos e pendências para as próximas etapas

- Admin comum ainda possui acesso global e não possui empresa.
- O acesso Inventory Brasil → LATAM/OXXO ainda é incidental, não explícito.
- Superuser não possui comportamento global uniforme em todos os filtros.
- Perfis funcionais globais e exceções por username precisam ser inventariados.
- O launcher da `.venv` precisa de reparo separado; não foi alterado no baseline.
- A suíte completa ainda precisa ser executada em etapa apropriada.
- A credencial removida do código continua potencialmente presente no histórico
  Git e não foi rotacionada.

## Compatibilidade

- Login e inicialização: validados com a credencial preservada no ambiente.
- Comportamento anterior dos perfis: preservado.
- Banco e dados: não alterados.
- Regras multi-tenant: não alteradas.

## Próxima etapa

Etapa 2 — Mapa de Ownership.
