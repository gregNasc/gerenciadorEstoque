# Etapa 6 — Corrigir o conceito de Admin

Data do checkpoint: 2026-09-05.

## Objetivo

Permitir que o role Admin possua uma Empresa principal, preservando a separação
conceitual e técnica entre Admin de tenant e Superuser da plataforma.

## Alterações realizadas

`Perfil.save()` não apaga mais `empresa` quando o role é Admin. A empresa
informada permanece persistida após qualquer salvamento do perfil.

Admins continuam sem limitação por Bases: ao salvar um Admin, suas `regionais`
são limpas. Gestores e Operadores continuam obrigatoriamente vinculados às
Bases usadas como escopo operacional.

No gerenciamento de usuários:

- Admin deixou de ser classificado como perfil global;
- criar ou editar Admin exige uma Empresa;
- Admin não exige seleção de Base;
- criar Admin não concede `is_superuser`;
- perfis funcionais globais mantiveram o comportamento anterior;
- Admins legados sem empresa continuam válidos durante a transição.

A fixture dos testes de contrato passou a criar `Admin + Empresa` pelo fluxo
normal de `Perfil.save()`, sem atualização direta no banco.

## Painel Superuser

O Django Admin existente em `/admin/` foi disponibilizado na barra lateral com
o rótulo `Painel Superuser`.

O link usa exclusivamente `request.user.is_superuser`. Um Admin de tenant não
vê o link e é recusado pelo Django Admin. Não foi criado nesta etapa o painel de
plataforma planejado para a Etapa 23.

## Estado do banco local

O diagnóstico encontrou:

- 1 Admin já vinculado a Empresa;
- 6 Admins legados sem Empresa;
- nenhuma Empresa foi inferida ou preenchida automaticamente.

Admins legados sem Empresa identificados:

- `admin`;
- `codex_qa_documentacao_20260825`;
- `edson.nunes`;
- `fabiano.andrade`;
- `felipe.tavares`;
- `julio.lima`.

Por decisão explícita, somente a conta `admin` permanece com
`is_superuser=True`. O status de Superuser foi removido de uma segunda conta.
Não foram alterados `is_staff`, status ativo, perfil, empresa ou senha dessa
conta. Os hashes das senhas foram verificados e preservados.

A conta `admin` está ativa, possui `is_staff=True` e foi validada pela regra de
autorização do Django Admin.

## Testes

Foram adicionados oito testes para validar:

- preservação da Empresa do Admin;
- remoção da limitação por Bases;
- compatibilidade de Admin legado sem Empresa;
- separação entre Superuser e role Admin;
- cadastro de Admin com Empresa e sem Base;
- rejeição de novo Admin sem Empresa;
- classificação correta na interface;
- acesso exclusivo do Superuser ao painel administrativo.

Suíte obrigatória da etapa:

```powershell
python manage.py test estoque.test_admin_company estoque.test_multitenant_contract estoque.test_user_access_profiles --keepdb -v 1
```

Resultado: 24 testes executados, 17 aprovados e 7 falhas esperadas do contrato;
suíte OK.

Validações estruturais:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
```

Resultado: zero inconsistências e nenhuma alteração de model sem migration.

Uma seleção ampliada de 31 testes executou os testes da etapa e de UI. Somente
um teste antigo da lista de Chamados falhou porque o template não contém mais o
texto `chamados encontrados`. A suíte completa também reencontrou a pendência
antiga do modal SICK registrada nas Etapas 4 e 5.

A tentativa de executar a suíte completa em paralelo não conseguiu emitir o
resumo porque o runner não serializa o traceback da falha antiga entre processos
sem suporte adicional. Nenhuma dessas falhas está nos arquivos ou fluxos
alterados pela Etapa 6.

## Migrations

Nenhuma. O campo `Perfil.empresa` já era nullable e compatível com o novo estado.

## Compatibilidade e pendências

- Superuser continua independente do role do Perfil;
- somente `admin` é Superuser no banco local;
- Admin Inventory Brasil mantém o acesso global legado durante a transição;
- `secure_queryset()` não foi restringido nesta etapa;
- os contratos de isolamento de Admin permanecem como falhas esperadas;
- os 6 Admins legados sem Empresa deverão ser tratados pela Etapa 7, sem
  adivinhação de tenant.

## Próxima etapa

Etapa 7 — Diagnóstico e backfill de Admins.
