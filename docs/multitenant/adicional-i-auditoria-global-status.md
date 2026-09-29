# Adicional I — Auditoria global de isolamento e configuração

## Status

Concluído em 29/09/2026.

## Escopo auditado

- querysets, formulários, views e APIs;
- notificações, comunicados e rotinas agendadas;
- SICK, chamados, compras, insumos e integrações;
- downloads, exportações Excel/PDF e arquivos privados;
- terminologia configurável no Tory e em relatórios de usuário;
- seletores operacionais de empresas e bases;
- referências históricas e compatibilidade com dados legados.

## Correções aplicadas

### Destinatários e rotinas agendadas

- Administradores de outros tenants não recebem mais comunicados de empresa,
  base, SICK, transferência, compras ou checklist.
- Superusers ativos continuam recebendo eventos globais permitidos.
- As notificações de manutenção prevista respeitam o escopo da empresa e a
  política de acesso ao SICK.
- Broadcast global sem empresa falha fechado para usuários que não sejam
  superuser.

### Metadados e filtros

- Categorias e regionais exibidas no SICK são derivadas apenas dos registros
  visíveis ao usuário.
- Bases de empresas inativas não entram em seletores operacionais.
- Seletores de integração, planejamento, compras e importação usam somente
  empresas ativas.

### Importação global de calendário

- A importação continua exclusiva do superuser.
- A empresa principal passou a ser obrigatória e explicitamente selecionada.
- A empresa alternativa para regionais terminadas em `X` é opcional, mas
  sempre explícita.
- Foram removidos os fallbacks por nome (`Inventory Brasil`, `OXXO`) e o uso
  arbitrário da primeira empresa cadastrada.
- Empresa ausente ou inativa é rejeitada antes da leitura do arquivo.

### Tory e relatórios

- Respostas e ações do Tory usam os termos configurados pelo tenant sem
  alterar categorias, intenções ou códigos técnicos internos.
- Exportações de inventário e chamados usam a terminologia configurável de
  regional e equipamento.
- Cabeçalhos técnicos usados em arquivos de reimportação permanecem estáveis
  por compatibilidade do protocolo.

### Áreas confirmadas como seguras

- Arquivos de equipamentos, chamados, compras e documentação são carregados
  somente após validação de escopo.
- Querysets de auditorias, ordens de serviço, compras, chamados, inventários e
  equipamentos passam pelas políticas de tenant correspondentes.
- Acesso compartilhado do suporte permanece restrito aos relacionamentos e
  capacidades explicitamente cadastrados.

## Compatibilidade histórica intencional

- O catálogo legado de `Insumo` permanece global porque o modelo não possui
  empresa proprietária. Registros operacionais e preços que possuem empresa
  continuam sujeitos às políticas de tenant.
- Identificadores externos do Portal Inventory Brasil e aliases de OXXO usados
  pela integração são dados do protocolo externo, não regras de autorização.
- Categorias e manuais históricos continuam preservados; novos cadastros e a
  apresentação ao usuário seguem a configuração da empresa.

## Testes adicionados

- comunicado de empresa não alcança administrador estrangeiro;
- comunicado por base inclui apenas usuários autorizados;
- manutenção prevista é separada por tenant;
- filtros SICK não revelam categoria ou regional estrangeira;
- Tory aplica terminologia do tenant sem mudar códigos internos;
- importação lista apenas empresas ativas;
- importação falha fechada sem empresa explícita;
- importação nunca infere empresa alternativa pelo nome;
- exportações de usuário aplicam terminologia do tenant.

## Validação

- bateria integrada multi-tenant: **137 testes aprovados** em 192,074 s;
- suíte completa: **626 testes aprovados** em 682,727 s;
- `python manage.py check`: sem problemas;
- `python manage.py makemigrations --check --dry-run`: nenhuma alteração;
- `git diff --check`: sem erros de conteúdo.

## Resultado

A auditoria global foi concluída sem vazamento conhecido entre tenants nos
fluxos revisados. Empresas inativas não aparecem em seletores operacionais,
operações globais sensíveis exigem superuser e o sistema não depende mais de
nomes de empresas para escolher o tenant durante a importação.

Conforme o plano, a próxima atividade é o Adicional J, dedicado à regressão
final. Ele não foi iniciado nesta etapa.
