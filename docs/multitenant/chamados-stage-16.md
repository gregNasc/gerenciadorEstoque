# Etapa 16 — Chamados

## Estado: concluída

O módulo de Chamados aplica o escopo multi-tenant desde a abertura até o
atendimento, as notificações e os eventos em tempo real. Permissão funcional e
escopo de dados permanecem decisões separadas.

## Regras aplicadas

- somente o Superuser possui visão global da plataforma;
- Admin acessa os Chamados da própria empresa e das empresas adicionais
  explicitamente autorizadas para a ação correspondente;
- acesso de visualização não concede atendimento, exportação ou administração;
- Gestor e Operador permanecem limitados às Bases vinculadas ao perfil;
- usuários de suporte podem atender o grupo Inventory Brasil, Inventory LATAM e
  OXXO somente quando o compartilhamento de suporte estiver configurado entre
  as empresas e houver permissão funcional de atendimento;
- Admin de empresa externa ao grupo não participa de filas, notificações ou
  eventos do grupo;
- grupos funcionais, por si só, não ampliam o tenant;
- IDs de Chamado, anexo, mensagem e transferência são resolvidos em querysets
  previamente filtrados pelo escopo autorizado;
- notas internas são visíveis apenas para quem pode atender o Chamado;
- configuração de líderes e aliases de inventário respeita empresa, Base e
  capability exata.

## Eventos e notificações

Os eventos WebSocket transportam `empresa_id` e `base_id`. A distribuição usa
grupos específicos por empresa, Base e usuário envolvido, além de um grupo
exclusivo de Superusers. Antes de entregar um evento, o consumer revalida a
permissão atual sobre o Chamado, protegendo também contra conexões abertas antes
de uma alteração de acesso.

As comunicações persistentes calculam destinatários por meio da mesma política.
Admins e atendentes de outros tenants não são incluídos implicitamente.

## Escopo coberto

- abertura e listagem de Chamados;
- fila, painel e filtros;
- detalhe, mensagens e notas internas;
- assumir, atender, transferir, resolver, cancelar e avaliar;
- anexos e download protegido;
- exportação;
- seleção de Bases, equipamentos, atendentes e supervisores;
- presença e eventos em tempo real;
- notificações e comunicados;
- integração de líderes e aliases com inventários do dia.

## Validação

- `manage.py check`: sem problemas;
- `makemigrations --check --dry-run`: nenhuma alteração pendente;
- 51 testes do módulo, do suporte Inventory e do isolamento da Etapa 16:
  aprovados;
- os cenários específicos cobrem visibilidade por empresa, capabilities por
  ação, IDs forjados, destinatários, suporte compartilhado, liderança e
  WebSockets;
- a auditoria do banco de desenvolvimento confirma que somente `admin` é
  Superuser;
- nenhuma senha é modificada por esta etapa.
