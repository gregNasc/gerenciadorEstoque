# Etapa 24 — onboarding e endurecimento final

## Resultado

A Etapa 24 conclui a evolução multi-tenant do plano oficial. O cadastro de uma
empresa agora ocorre em um onboarding exclusivo do Superuser e o tenant só é
ativado depois das validações finais.

## Onboarding "Nova Empresa"

O fluxo implementado possui seis passos:

1. dados básicos e slug único;
2. seleção explícita dos módulos;
3. criação do primeiro Admin, sempre sem `is_staff` e sem `is_superuser`;
4. criação opcional de bases;
5. relacionamentos direcionais opcionais;
6. revisão e ativação do tenant.

O cancelamento conserva o tenant incompleto como inativo para retomada. A
ativação exige pelo menos um módulo explicitamente configurado e um Admin ativo.
Uma opção de compartilhamento de suporte cria tanto o marcador do relacionamento
quanto a capability `CHAMADOS:ATENDER`; desmarcá-la desativa essa capability.

O fluxo não altera senhas existentes. Apenas o Superuser cria a senha inicial do
primeiro Admin durante o cadastro de um tenant novo.

## Endurecimento

- `Empresa.slug` é obrigatório e único. A migração `0051` preenche slugs ausentes
  antes de aplicar a restrição.
- Um perfil ativo que não seja Superuser é inválido sem empresa no `full_clean()`.
- O middleware bloqueia por padrão usuários autenticados sem tenant ativo,
  permitindo somente o logout.
- Relações M2M de bases (`regionais` e `bases_checklist`) rejeitam bases que não
  pertençam à empresa principal do perfil.
- O alias legado `request.empresa` foi removido; `request.tenant`,
  `request.tenant_scope` e `request.tenant_context` são as APIs canônicas.
- Preços e pesquisas online legados sem empresa não recebem mais fallback pela
  empresa atual do autor. Eles permanecem visíveis somente no escopo explícito
  do Superuser.
- A equipe `SICK_MANUTENCAO` atua em todas as bases da própria empresa, sem
  atravessar tenant, inclusive na O.S. vinculada.
- Um SICK fora do escopo gera negação de acesso explícita, sem erro interno nem
  confirmação da existência do registro.
- O exportador Excel converte rótulos traduzíveis em texto antes de gravá-los.

## Auditoria final A/B

Os testes criam empresas independentes A e B e exercitam os canais exigidos pelo
plano:

| Canal | Cobertura principal |
| --- | --- |
| URL e IDs manipulados | `estoque.test_inventory_tenant_isolation`, `insumos.test_tenant_isolation_stage15` |
| Formulários | `insumos.test_tenant_isolation_stage15`, `compras.test_tenant_isolation_stage17` |
| API e AJAX | `estoque.test_inventory_tenant_isolation`, `estoque.test_tenant_feature_enforcement_stage22` |
| Exportações | `estoque.test_inventory_tenant_isolation`, `integracao.tests.test_tenant_isolation_stage19` |
| Arquivos privados | `estoque.test_tenant_isolation_stage18` |
| WebSocket | `chamados.test_tenant_isolation_stage16`, `estoque.test_tenant_feature_enforcement_stage22` |
| Tory | `estoque.test_tory_tenant_isolation_stage20` |
| Integrações | `integracao.tests.test_tenant_isolation_stage19` |

O acesso a B falha em todos esses canais para usuários de A, salvo quando existe
relacionamento direcional, seleção adicional no perfil e capability exata para o
recurso e a ação.

## Validação executada

- suíte completa criada do zero: **557 testes aprovados**;
- `python manage.py check`: sem problemas;
- `python manage.py makemigrations --check --dry-run`: nenhuma alteração pendente;
- migração `estoque.0051_empresa_slug_unico`: aplicada com sucesso;
- painel e onboarding acessados pelo Superuser `admin`: HTTP 200;
- Superusers no banco real: somente `admin`;
- estado preservado: 4 empresas ativas, 11 módulos, 44 configurações, 2
  relacionamentos ativos e módulos `insumos`, `checklist` e `tory` desabilitados
  para ATROPIC.

Há um usuário QA legado ativo sem empresa. Ele não foi associado por inferência
nem teve credenciais alteradas; o middleware o bloqueia até que o Superuser faça
uma associação explícita ou o desative.
