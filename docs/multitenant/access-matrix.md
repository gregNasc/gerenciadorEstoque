# Matriz de acesso atual

## Status

- Etapa: 3 — Matriz de acesso atual
- Estado: concluída
- Data: 2026-09-04
- Escopo: comportamento efetivo antes do endurecimento multi-tenant
- Alterações de regras, schema ou dados: nenhuma

## Legenda

- **R**: visualizar/listar/detalhar.
- **C**: criar.
- **E**: editar ou alterar estado.
- **M**: movimentar, transferir, receber ou devolver.
- **A**: aprovar, autorizar, finalizar ou regularizar.
- **X**: exportar ou baixar arquivo.
- **ADM**: administrar configuração, usuários ou catálogo.
- **Base**: somente Bases explicitamente vinculadas ao Perfil.
- **Global atual**: todas as Empresas, sem relacionamento persistido.

Uma letra na matriz registra capacidade encontrada no código. Ela não garante
que todos os estados de negócio aceitem a ação, nem que todas as views do módulo
implementem o escopo de forma uniforme.

## Regra organizacional confirmada

Inventory Brasil, Inventory LATAM e OXXO devem ser tratados como uma exceção
organizacional única para o **Admin da Inventory Brasil**:

```text
Admin Inventory Brasil
    ├── Inventory Brasil: acesso completo
    ├── Inventory LATAM: acesso completo
    └── OXXO: acesso completo
```

“Acesso completo” inclui leitura, criação, edição, movimentação, atendimento,
aprovação, exportação e administração operacional, respeitadas apenas regras de
negócio específicas do fluxo.

Essa exceção não concede acesso às demais Empresas e não transforma todo Admin
em administrador global. Gestores e Operadores, inclusive nessas três divisões,
continuam vinculados às Bases atribuídas ao Perfil.

A implementação futura não pode depender dos nomes acima nem de IDs fixos. O
agrupamento precisa ser persistido e auditável. Até isso existir, esta seção é
uma regra de contrato, não uma nova regra aplicada pelo código nesta etapa.

## Matriz conceitual: estado atual versus regra requerida

| Perfil | Própria empresa/base | Inventory Brasil | Inventory LATAM | OXXO | Outras empresas |
|---|---|---|---|---|---|
| Superuser | RW/ADM | RW/ADM | RW/ADM | RW/ADM | RW/ADM |
| Admin Inventory Brasil — atual | RW/ADM | RW/ADM | RW/ADM | RW/ADM | **RW/ADM indevido** |
| Admin Inventory Brasil — requerido | RW/ADM | RW/ADM | RW/ADM | RW/ADM | não |
| Admin de outra Empresa — atual | RW/ADM | **RW/ADM indevido** | **RW/ADM indevido** | **RW/ADM indevido** | RW/ADM global |
| Admin de outra Empresa — requerido | RW/ADM | não | não | não | não |
| Gestor | RW conforme Bases e fluxo | somente Bases atribuídas | somente Bases atribuídas | somente Bases atribuídas | somente Bases atribuídas |
| Operador | operação limitada às Bases | somente Bases atribuídas | somente Bases atribuídas | somente Bases atribuídas | somente Bases atribuídas |
| Perfil funcional | depende do grupo/permissão | inconsistente | inconsistente | inconsistente | alguns caminhos globais |

Não há atualmente Admin cadastrado para Inventory LATAM ou OXXO. Se esses roles
forem criados no futuro, não devem receber automaticamente a exceção do Admin da
Inventory Brasil sem decisão explícita.

## Estado agregado dos perfis no banco validado

| Item | Quantidade/estado |
|---|---:|
| Perfis com role Admin | 7 |
| Superusers entre esses Admins | 2 |
| Admins comuns | 5 |
| Admin comum associado à Inventory Brasil | 1 |
| Admins comuns sem Empresa | 4 |
| Admin associado à Inventory LATAM | 0 |
| Admin associado à OXXO | 0 |
| Gestores | 24, todos com Empresa |
| Operadores | 3, sendo 1 sem Empresa |
| Vínculos Perfil → Base | 59 |
| Vínculos a Base fora da Empresa principal | 0 |
| Perfis com escopo adicional de Compras por Empresa | 0 |
| Perfis com escopo adicional de Compras por Base | 0 |

Existe um Operador no grupo `INSUMOS_COMPRAS`, sem Empresa e sem escopos de
Compras persistidos. Como esse grupo torna o perfil funcional global em vários
endpoints de Insumos, seu alcance atual é inconsistente entre módulos.

## Matriz por domínio

### Identidade, usuários e empresas

| Perfil | Leitura | Escrita/administração | Escopo atual |
|---|---|---|---|
| Superuser | usuários e Django Admin | administração global Django | global |
| Admin | usuários, Empresas e Bases | cria/edita/inativa usuários e concede permissões | global para qualquer Admin |
| Gestor | sem administração de usuários | não | — |
| Operador | sem administração de usuários | não | — |

`cadastrar_usuario` e `gerenciar_usuarios` verificam somente o role Admin. Um
Admin comum, sem `is_staff` e sem `is_superuser`, pode administrar usuários de
qualquer Empresa. Os formulários carregam `Empresa.objects.all()` e
`Base.objects.all()`. Criar ou salvar um Admin normalmente remove sua Empresa e
suas Bases por `Perfil.save()`.

### Equipamentos e estoque

| Perfil | Capacidades atuais | Escopo efetivo |
|---|---|---|
| Superuser | R/C/E/M/X quando passa pelas permissões/decorators | global em helpers que reconhecem `is_superuser`; inconsistente nos que só usam role |
| Admin | R/C/E/M/A/X | global atual; pode selecionar e reatribuir qualquer Base |
| Gestor | R/C/E/M conforme role/permissão | Empresa principal + Bases vinculadas em `secure_queryset()` |
| Operador | normalmente bloqueado; permissões podem liberar ações específicas | Bases vinculadas quando o endpoint usa helper seguro |
| Compras funcional | catálogo, cadastro e preços conforme grupo/permissão | catálogo global; ativos dependem do escopo de Compras |

`secure_queryset()` filtra Gestor e Operador por Empresa e Bases, mas retorna o
QuerySet inteiro para qualquer Admin. Durante auditoria ativa, equipamentos da
Base auditada são ocultados inclusive para Admin.

### Solicitações, transferências e empréstimos

| Perfil | Capacidades atuais | Escopo efetivo |
|---|---|---|
| Superuser/Admin | R/C/E/M/A | global atual sobre origem e destino |
| Gestor | cria solicitação; visualiza e movimenta fluxos ligados às Bases | Bases vinculadas, com destinos oferecidos globalmente em alguns formulários |
| Operador | recebe/transfere quando role, rota ou permissão permite | Base de origem/destino vinculada na maioria dos fluxos |

Pontos relevantes:

- Admin pode separar, enviar, receber, cancelar, recusar e aprovar fluxos de
  qualquer Empresa.
- `TransferenciaForm` oferece qualquer Base diferente da origem como destino;
  isso permite fluxo cross-tenant quando a view chamadora não restringe.
- Empréstimo restringe a origem às Bases do usuário, mas oferece todas as Bases
  como destino e valida apenas `GrupoRegional`. Hoje não há GrupoRegional com
  Bases de Empresas diferentes, portanto não foi observado cross-tenant real
  nesse fluxo no banco validado.
- `solicitar_transferencia_lote` exige apenas login, aceita IDs de Equipamento
  sem QuerySet seguro e cria solicitações usando a primeira Base do usuário.
- Algumas views usam `perfil.is_admin()` embora `is_admin` seja property; esses
  caminhos podem falhar antes de aplicar a regra pretendida.

### SICK e manutenção

| Perfil | Capacidades atuais | Escopo efetivo |
|---|---|---|
| Admin | R/E/M/A | global, exceto restrições específicas da manutenção matriz |
| Gestor | cria e opera SICK | Equipamentos das Bases vinculadas |
| Operador | cria/opera etapas permitidas | Bases vinculadas e permissões/grupos |
| Técnicos especiais | manutenção e O.S. específicas | existem grupos e exceções por username |

O grupo `SICK_MANUTENCAO` possui visão operacional ampliada. Há também exceções
por username em SICK e O.S.; elas não são uma regra segura de tenant e precisam
ser substituídas sem perder o fluxo operacional necessário.

### Insumos, inventários e checklists

| Perfil | Capacidades atuais | Escopo efetivo |
|---|---|---|
| Superuser | R/C/E/A/X | global em vários endpoints |
| Admin | R/C/E/A/X | global em Estoque/Insumos/Inventários; inconsistente em Checklists |
| Gestor | solicita, consulta e executa checklists | Bases vinculadas |
| Operador | consulta/preenche conforme permissões | Bases e `bases_checklist` vinculadas |
| Compras/Planejamento/Financeiro/Executivo | capacidades funcionais específicas | alguns endpoints usam alcance global por grupo |

Inconsistências confirmadas:

- `Perfil.pode_ver_empresas_globais` retorna verdadeiro para qualquer Admin e
  para Compras, Planejamento, Financeiro ou Executivo.
- Listagens de Inventário e KPIs usam essa property para retornar todas as
  Empresas.
- Edição de Inventário permite Admin ou Planejamento editar qualquer registro
  quando o perfil é considerado global.
- A listagem de Checklists retorna vazio para Admin sem Empresa, mas os helpers
  de detalhe/mutação consideram esse mesmo Admin autorizado a qualquer
  Checklist. Manipular o ID pode alcançar um registro que não aparece na lista.
- O export geral de Inventários não aplica qualquer escopo, role ou permissão.

### Auditorias

| Perfil | Capacidades atuais | Escopo efetivo |
|---|---|---|
| Superuser/Admin | R/C/E/A/M/X | global sobre todas as Empresas |
| Gestor/Operador com Base | coleta, envio, resposta e relatório liberado | Empresa principal + Bases vinculadas |

`usuario_e_admin()` trata Superuser e qualquer role Admin como equivalentes.
Admins criam/editam/cancelam campanhas, alteram Bases, validam resultados,
regularizam divergências, criam transferências e exportam campanhas de qualquer
Empresa. Usuários de Base veem somente campanhas/auditorias filtradas por sua
Empresa e Bases.

### Chamados, anexos e WebSockets

| Perfil | Capacidades atuais | Escopo efetivo |
|---|---|---|
| Superuser/Admin | R/C/E/A/X/ADM, atendimento e supervisão | global atual |
| Gestor | abre e acompanha; pode atender se possuir grupo/permissão | Bases vinculadas e reparações da Empresa principal |
| Operador | abre chamado operacional e acompanha os próprios | Bases vinculadas; grupos podem liberar atendimento |
| Suporte/Supervisor | atende/supervisiona conforme grupo | Bases vinculadas, salvo Admin |

Admin enxerga todos os Chamados, pode atender, supervisionar, configurar e
exportar. No WebSocket, Admin entra no grupo global `chamados_admins`; atendentes
comuns entram em grupos por Base. O chat valida o Chamado pelo mesmo QuerySet da
policy. Anexos verificam acesso ao Chamado e notas internas verificam capacidade
de atendimento.

### Compras, catálogo e preços

| Perfil | Capacidades atuais | Escopo efetivo |
|---|---|---|
| Superuser/Admin | R/C/E/A/M/X/ADM | todas as Empresas, Bases, aquisições e remessas |
| Compras funcional | catálogo, fornecedores, preços e remessas | Empresas/Bases delegadas; catálogo e preço são globais |
| Financeiro/Executivo | visualização de valores | alcance varia conforme endpoint e escopos adicionais |
| Gestor/Operador | confirmação/ações quando envolvidos ou com permissão | Bases operacionais vinculadas |

Qualquer Admin recebe `Empresa.objects.all()` e `Base.objects.all()` pela policy
de Compras. Perfis não Admin dependem de `empresas_escopo_compras` e
`bases_escopo_compras`, mas esses relacionamentos estão vazios no banco atual.
Produto, Insumo, Fornecedor e históricos de preço continuam globais.

### Ordens de serviço

| Perfil | Capacidades atuais | Escopo efetivo |
|---|---|---|
| Superuser/Admin | R/A/X | todas as O.S. |
| Gestor | R e autorização | O.S. em que é envolvido ou cujas Bases estão vinculadas |
| Operador | R quando envolvido/na Base; assinatura conforme fluxo | Bases vinculadas |
| Compras funcional | R de O.S. ligadas ao usuário ou Bases de Compras | escopo delegado |

Existem exceções por username: um usuário vê todas as O.S. SICK; outro vê todas
as O.S. de Transferência, Empréstimo e SICK, independentemente de Empresa. Essa
exceção é global por tipo e não por tenant.

### Integração Inventory Planning

| Perfil | Capacidades atuais | Escopo efetivo |
|---|---|---|
| Qualquer role com `gerenciar_mapeamentos_planning` | R/E/ADM dos bindings | global, sem filtro de tenant |
| Qualquer role com permissão adicional de materialização | C/E | global sobre eventos resolvidos |

A autorização é baseada apenas em permissões Django específicas. Um Operador
pode receber a permissão e administrar clientes, regiões e qualquer Base do
sistema, pois a view usa QuerySets globais. Isso pode ser legítimo para uma
função de plataforma, mas precisa ser explicitamente separado de um Operador de
tenant.

### Tory

| Perfil | Capacidades atuais | Escopo efetivo |
|---|---|---|
| Admin | consultas de equipamentos, inventários, transferências e empréstimos | global atual |
| Gestor/Operador | consultas operacionais | Empresa principal + Bases vinculadas nos helpers testados |
| Perfis funcionais | consultas conforme intenção e módulo | variável; alguns caminhos de Insumos são globais |

Há testes que impedem Gestor de consultar equipamentos, inventários e nomes de
Bases fora do escopo. Porém Admin usa `Base.objects.all()`, transferências e
empréstimos globais. A Tory ainda não recebe um Tenant Scope central.

## Matriz específica de exportações e arquivos

| Recurso | Proteção atual | Resultado cross-tenant atual |
|---|---|---|
| Histórico de equipamentos Excel/PDF | role Admin | qualquer Admin exporta global |
| Chamados XLSX | policy de Chamados | Admin exporta global; demais ficam no QuerySet autorizado |
| Auditoria de Base XLSX | auditoria visível; finalização para não Admin | Admin global; usuário de Base restrito |
| Auditoria de Campanha XLSX | Admin | global para qualquer Admin |
| Inventários XLSX | somente `login_required` | **qualquer autenticado exporta todos** |
| Checklist modelo XLSX | helper de acesso ao Checklist | Admin sem Empresa alcança qualquer ID |
| Anexo de Chamado | acesso ao Chamado e nota interna | segue policy; Admin global |
| Documento/driver global | conteúdo de plataforma | autenticado conforme views atuais |
| Arquivo de mensagem/comunicado | depende do objeto/usuário | sem Tenant Scope central |

## Risco concreto confirmado no export de Inventários

`insumos:exportar_excel` está publicado, exige apenas autenticação e consulta
todos os Inventários planejados ou em andamento.

Reprodução somente leitura no banco validado:

- usuário sintético autenticado, sem Perfil;
- resposta HTTP 200 com XLSX;
- 4.776 Inventários considerados pelo export;
- dados distribuídos em 2 Empresas.

Essa é uma falha preexistente de isolamento. Ela não foi corrigida nesta etapa
porque uma correção definitiva precisa consumir o Tenant Scope autorizado e
preservar a exceção Inventory Brasil/LATAM/OXXO sem hardcode.

## Outras falhas e exceções relevantes

- Todo Admin comum é tratado como global em vários módulos.
- O acesso inverso LATAM/OXXO → Inventory Brasil seria concedido a qualquer
  futuro Admin dessas divisões pelo código atual, contrariando a regra requerida.
- O vínculo do único Admin da Inventory Brasil é instável: um `save()` normal do
  Perfil remove sua Empresa.
- Há endpoints AJAX e de mutação que buscam objetos diretamente por ID antes de
  aplicar ou sem aplicar QuerySet seguro.
- Há permissões funcionais globais sem Empresa/escopo persistido.
- Há regras baseadas em username para O.S. e manutenção.
- UI, menu e decorators de role não são uniformes com as policies de objeto.
- Superuser é global em policies que verificam `is_superuser`, mas pode ser
  bloqueado ou esvaziado em helpers que exigem `perfil.is_admin` ou Empresa.

## Comportamento mínimo que precisa ser preservado

1. Superuser mantém acesso global da plataforma.
2. Admin da Inventory Brasil mantém acesso completo a Inventory Brasil,
   Inventory LATAM e OXXO.
3. Admin da Inventory Brasil deixa de acessar qualquer quarta Empresa.
4. Admin de qualquer outra Empresa acessa somente sua própria Empresa.
5. Nenhum acesso inverso é criado automaticamente para Admin LATAM/OXXO.
6. Gestor e Operador continuam vinculados às Bases, não ao agrupamento inteiro.
7. Grupos e permissões funcionais não ampliam tenant automaticamente.
8. Escrita cross-tenant fora da exceção organizacional exige capability
   explícita do fluxo.

## Validação da etapa

```text
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test \
  estoque.test_user_access_profiles \
  estoque.tests.ToryIsolamentoBasesTests \
  chamados.tests.ChamadosIntegracaoTests \
  chamados.tests.ChamadoWebSocketTests \
  auditorias.tests.test_core.CampanhaMultiBaseTests \
  compras.tests.PrecificacaoProdutoTests \
  integracao.tests.test_bindings.MappingPermissionAndRunTests \
  ordens_servico.test_permissions_special \
  --keepdb
```

Resultados:

- system check: OK, zero issues;
- alterações de model sem migration: nenhuma;
- testes focados: 72 executados, 72 aprovados;
- suíte completa: não executada nesta etapa.

## Próxima etapa

Etapa 4 — Testes de contrato multi-tenant.
