# Etapa 18 — Histórico, Auditoria, documentação e arquivos

## Estado: concluída

Históricos, auditorias, documentação e arquivos privados agora são resolvidos
sempre a partir do usuário autenticado, da empresa ou Base proprietária e da
ação exata solicitada. Conhecer uma URL ou um identificador não autoriza o
acesso ao conteúdo.

## Regras de acesso

- somente o Superuser possui visão global da plataforma;
- Admin possui acesso integral apenas à própria empresa;
- uma empresa adicional exige relacionamento explícito e capability para a
  ação executada;
- Inventory Brasil, Inventory LATAM e OXXO não compartilham dados
  automaticamente: toda combinação continua explícita e direcional;
- Gestores e Operadores continuam restritos às Bases vinculadas;
- o usuário de suporte do grupo Inventory conserva a exceção somente em
  Chamados; ela não amplia auditorias, documentação ou outros arquivos;
- a identificação externa é procurada apenas dentro de um queryset já
  autorizado, resultando em `404` fora do escopo;
- as ações `VISUALIZAR`, `CRIAR`, `EDITAR`, `APROVAR`, `EXPORTAR` e
  `ADMINISTRAR` são avaliadas separadamente quando aplicáveis.

## Matriz de propriedade dos arquivos

| Arquivo ou documento | Proprietário/escopo | Entrega |
| --- | --- | --- |
| Foto e QR Code de equipamento | Base e empresa do equipamento | Rota autenticada e filtrada por tenant |
| DANFE e XML de aquisição | Empresa da aquisição | Rota autenticada com capability `EXPORTAR` |
| Declaração de Correios | Transferência/empréstimo e suas Bases autorizadas | Rota autenticada e filtrada pela operação |
| Anexo de comunicado | Destinatário, empresa ou público global criado pelo Superuser | Rota autenticada; broadcast de tenant não atravessa empresas |
| Anexo de mensagem | Remetente e destinatário | Rota autenticada; o ID isolado não concede acesso |
| Anexo de chamado | Empresa/Base do chamado e regra explícita de suporte | Armazenamento privado e rota autenticada |
| Anexo de Ordem de Serviço | Empresa/Base da O.S. | Rota autenticada com capability `EXPORTAR` |
| Checklist de cliente | Cliente e empresa | Um documento por combinação cliente/empresa |
| Resolução, vídeo e driver | Empresa; `empresa = NULL` somente para legado global da plataforma | Consulta por policy; mutações de tenant nunca alteram o legado global |
| Manuais estáticos oficiais | Plataforma | Arquivo estático público, sem dados de tenant |

O projeto não publica `MEDIA_URL` nas rotas Django, inclusive em
desenvolvimento. Arquivos enviados por usuários são entregues por views que
revalidam autenticação e escopo e usam `Cache-Control: private, no-store` e
`X-Content-Type-Options: nosniff` quando retornam o conteúdo persistido.

Não há mecanismo de URL assinada no projeto nesta etapa. A proteção adotada é
autorização no momento de cada download, de modo que uma URL copiada não
funciona para outro usuário sem o mesmo escopo.

## Histórico, logs e auditorias

- campanhas, auditorias e divergências são filtradas por empresa antes da
  busca por identificador;
- criação, correção, validação, aprovação, regularização, inativação e
  exportação exigem a capability exata da empresa auditada;
- a transferência gerada por auditoria é autorizada pela Base auditada e
  continua limitada à mesma empresa;
- históricos de equipamento usam o escopo do equipamento/Base e não oferecem
  catálogo de produto de outra empresa em seus formulários;
- exports e relatórios são gerados somente depois da resolução do tenant;
- eventos e registros existentes continuam associados aos seus objetos de
  domínio; nenhum dado histórico foi duplicado ou reatribuído por nome.

## Documentação e compatibilidade legada

Vídeos, resoluções e drivers receberam uma empresa proprietária opcional. Um
Admin autenticado cria e gerencia documentos da própria empresa; documentos
globais legados são somente leitura para tenants e administráveis apenas pelo
Superuser.

O checklist de cliente passou de um registro único por cliente para um registro
por `(cliente, empresa)`. A migração atribui automaticamente a empresa quando
os inventários do cliente apontam inequivocamente para um único tenant. Um
legado ambíguo permaneceria global, somente leitura, e ainda seria visível
apenas a uma empresa que possua inventário daquele cliente.

Auditoria após a migração no banco de desenvolvimento:

- 2 checklists associados a empresas;
- 1 vídeo global legado;
- 1 driver global legado;
- nenhuma resolução global ou empresarial existente;
- apenas o usuário `admin` é Superuser.

Nenhuma senha foi modificada.

## Migrações

- `estoque.0049_documentacao_por_empresa`;
- `insumos.0037_checklist_documento_por_empresa`.

## Validação

- `manage.py check`: sem problemas;
- `makemigrations --check --dry-run`: nenhuma alteração pendente;
- 29 testes de documentação e isolamento específico da Etapa 18: aprovados;
- 39 testes de auditorias, declarações, comunicados e históricos: aprovados;
- 28 testes de chamados, suporte Inventory, compras e Ordens de Serviço:
  aprovados;
- total das baterias direcionadas: 96 testes aprovados;
- migrations aplicadas no banco de desenvolvimento;
- fixtures de Chamados tornadas idempotentes para respeitar os grupos já
  criados pelas migrations;
- nenhum upload persistido possui referência direta a `.url` nos templates ou
  views auditados.
