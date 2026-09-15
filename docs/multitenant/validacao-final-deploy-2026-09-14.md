# Validação final e deploy controlado — 2026-09-14

## Identificação da release

- Branch: `main`
- Commit inicial validado: `b48a0d6ebb6d7e00af6b48c24d8dc735fb957e63`
- Commit final publicado: `b688b4363d6dd44729ea135f6ba5ea4525cadc52`
- Início da validação: `2026-09-14 14:17:29 -03:00`
- Conclusão da validação: `2026-09-14 23:20 -03:00`
- Situação: concluída, com riscos de segurança aceitos e registrados

## Blocos concluídos

### Repositório

- `git status`: limpo no início da validação.
- `main` local confirmado no mesmo commit de `origin/main` por consulta remota.
- Migrations `estoque.0043` até `estoque.0051` versionadas.

### Django e migrations

- `python manage.py showmigrations`: todas as migrations aplicadas no banco local configurado.
- `python manage.py makemigrations --check --dry-run`: `No changes detected`.
- `python manage.py migrate --plan`: nenhuma operação pendente.
- `python manage.py check`: nenhum problema identificado.

### Testes automatizados

- Total: 557 testes.
- Duração: 352,314 segundos.
- Execução: quatro processos paralelos, em bancos de teste isolados.
- Resultado: `OK`.

A suíte cobre, entre outros pontos:

- Administrador de empresa única e Administrador multiempresa;
- rejeição de empresas não relacionadas;
- alteração manual de IDs e acesso direto a dados externos;
- equipamentos, histórico, transferências, Sick e empréstimos;
- usuários e perfis;
- chamados e suporte compartilhado do grupo Inventory;
- compras e Valor de Equipamentos;
- APIs, integrações e endpoints internos;
- Tory e rejeição de escopo forjado.

### Auditoria local de integridade

- Banco identificado como local, não Render.
- Quatro empresas ativas.
- Somente o usuário `admin` é Superuser.
- Nenhum vínculo de regional ou base de checklist cruza tenants.
- Existe um Admin legado ativo sem empresa somente no banco local. O usuário confirmou que esse registro não existe no Render; não foi alterado e não bloqueia o deploy.

### Simulação de configuração de produção

- `check --deploy` executado com configuração temporária de produção e banco em memória.
- Cookies seguros, redirecionamento HTTPS, CSRF e exigência de `SECRET_KEY` foram validados.
- Aviso remanescente: HSTS fica desabilitado se `SECURE_HSTS_SECONDS` não estiver definido. A variável deve ser conferida no Render antes de qualquer decisão, pois habilitar HSTS por período longo não deve ser feito automaticamente.

## Validação no Render

- Serviço: `gerenciadorEstoque`.
- URL: `https://gerenciadorestoque.onrender.com`.
- Commit multi-tenant inicialmente publicado: `b48a0d6ebb6d7e00af6b48c24d8dc735fb957e63`.
- Commit final publicado após duas correções de runtime: `b688b4363d6dd44729ea135f6ba5ea4525cadc52`.
- Deploy manual iniciado em `2026-09-14 14:03:51 -03:00` e concluído em 2m11s.
- `collectstatic`: 187 arquivos copiados e 535 pós-processados.
- Migrations `estoque.0050` e `estoque.0051`: aplicadas com `OK` às `14:04:47 -03:00`.
- Uvicorn iniciou e o serviço foi declarado Live às `14:06:03 -03:00`.
- Banco `estoque_db`: PostgreSQL 18, disponível, com recuperação ponto-a-ponto dos últimos 7 dias.
- Export lógico completo solicitado em `2026-09-14 14:27 -03:00` e concluído por volta de `14:28 -03:00`.

### Segurança pública

- HTTP redireciona para HTTPS com 301.
- Login HTTPS responde 200.
- Cookie CSRF possui atributo `Secure`.
- `X-Content-Type-Options: nosniff`.
- `X-Frame-Options: DENY`.
- `DEBUG=False` confirmado no ambiente do Render.
- `check --deploy` apontou `security.W004` (HSTS não configurado) e `security.W009` (força da `SECRET_KEY`).
- A `SECRET_KEY` atual foi mantida por decisão expressa do responsável. Seu valor não foi exibido nem registrado.
- HSTS permaneceu desabilitado para evitar uma alteração de segurança com efeito persistente sem uma janela própria de implantação.
- Os dois avisos são riscos aceitos para esta publicação e não bloquearam os testes funcionais.

### Correções realizadas durante a validação

1. O Uvicorn iniciou sem uma implementação de protocolo WebSocket instalada. O endpoint
   `/ws/chamados/presenca/` recebeu tentativas de upgrade não suportadas e respondeu 404.
   Foi adicionada a dependência `websockets==17.1`, commit `789a65f23b94916474d64a4a2da1d569756b8431`.
   O deploy concluiu em 1m55s e os logs passaram a registrar `WebSocket ... [accepted]` e
   `connection open`.
2. O smoke test encontrou `500 Internal Server Error` em `/estoque/api/kpis/`. O traceback
   confirmou `TypeError: keys must be str, int, float, bool or None, not __proxy__`: nomes
   traduzíveis criados por `gettext_lazy` estavam sendo usados como chaves do JSON.
   As chaves foram convertidas explicitamente para texto e foi adicionado um teste de
   regressão, commit `b688b4363d6dd44729ea135f6ba5ea4525cadc52`.

O teste de regressão e os dois testes existentes do mesmo fluxo passaram. O deploy corretivo
final concluiu em 2m12s, sem migrations pendentes, e o endpoint afetado respondeu `200 OK`.

## Auditoria de dados em produção

- Três empresas cadastradas e ativas: Inventory Brasil, Inventory Latam e OXXO.
- Somente o usuário `admin` é Superuser.
- Nenhum usuário ativo ou Admin comum sem empresa.
- Nenhuma regional e nenhum checklist com vínculo cruzado entre empresas.
- 24 Gestores e 2 Operadores; nenhum deles com escopo efetivo diferente de sua empresa.
- Administradores multiempresa possuem somente combinações permitidas dentro do grupo Inventory.
- `everaldo.macedo`, Admin de Inventory Latam, enxerga somente Inventory Latam.
- O Superuser `admin` enxerga as três empresas do grupo.
- Não existe a empresa de teste local nem o usuário legado citado no banco do Render.
- Registros históricos/globais sem empresa foram contabilizados e preservados; não foi feita
  atribuição em massa sem regra de negócio.

## Smoke tests em produção

Rotas principais validadas com o Superuser autenticado:

- dashboard, estoque, histórico, transferências e Sick;
- Chamados e dashboard de Chamados;
- painel de Superuser e cadastro de usuários;
- Insumos, inventários e checklists;
- Compras e Valor de Equipamentos;
- Ordens de Serviço, empréstimos, solicitações e checklist;
- Assistente Operacional (Tory).

APIs de regionais, equipamentos, Chamados, KPIs de inventários e BI responderam `200 OK`.
O endpoint de KPIs do estoque também respondeu `200 OK` depois da correção. Rotas de detalhe
com identificadores inexistentes retornaram negação segura (`404`) nos módulos que exigem um
objeto real, sem `500`.

Uma consulta simples ao Tory (`Quantos equipamentos existem?`) respondeu `200 OK` e exibiu
o resumo do escopo visível do Superuser. O resultado confirmou 1.173 equipamentos visíveis,
com distribuição por status, finalidade e categoria.

## Encerramento

- Serviço final: `Live` no commit `b688b4363d6dd44729ea135f6ba5ea4525cadc52`.
- Backup lógico e recuperação ponto-a-ponto disponíveis antes das correções.
- Nenhuma migration nova foi criada ou aplicada durante os deploys corretivos.
- WebSocket funcional após a inclusão da dependência de runtime.
- Nenhum traceback, resposta 500 ou erro de upgrade observado nos logs do processo final.
- Alterações de senha: nenhuma.
- `SECRET_KEY`: mantida conforme solicitado.
