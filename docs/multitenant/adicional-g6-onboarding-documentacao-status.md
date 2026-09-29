# Adicional G.6 — Documentação no onboarding

## Status

Concluído.

## Implementação

- A etapa `documentacao` deixou de ser apenas informativa.
- Quando o módulo `documentacao` está desabilitado, a etapa é pulada e nenhuma configuração é criada ou herdada.
- Quando o módulo está habilitado, o Superuser pode configurar individualmente:
  - Biblioteca;
  - Manuais de equipamentos;
  - Drivers;
  - Resolução de problemas;
  - Checklist de clientes;
  - Vídeos.
- Cada seção pode ser habilitada ou desabilitada e receber um nome de apresentação próprio.
- Nome de apresentação vazio mantém o rótulo padrão definido pelo código estável da seção.
- O catálogo e a própria etapa documental seguem diretamente para o Primeiro Admin quando o módulo está desligado.
- Configurações existentes são preservadas quando o módulo é desabilitado, permitindo reativação posterior sem perda de dados.

## Segurança multi-tenant

- Somente os seis códigos oficiais do model são processados.
- Campos ou códigos injetados pelo navegador são ignorados.
- Todas as gravações usam exclusivamente a empresa em onboarding, resolvida no backend.
- A validação é atômica; um nome inválido impede alterações parciais.
- Nenhuma seção é habilitada automaticamente.
- `permite_conteudo_global_legado` permanece desabilitado para registros novos e não é exposto no onboarding.
- Nenhuma configuração de outra empresa é alterada.
- Nenhuma senha ou `SECRET_KEY` foi alterada.

## Endurecimento adicional — empresas inativas

- Empresas inativas foram removidas dos seletores operacionais de empresa.
- A regra é aplicada no backend aos escopos de empresa, base, catálogo/compras, documentação e comunicações.
- O seletor de empresa do Dashboard rejeita também o ID inativo informado manualmente na URL.
- Cadastro e edição de usuários não aceitam empresa principal ou adicional inativa.
- Relacionamentos inativos ou ligados a tenants inativos não aparecem como opções de atribuição.
- O onboarding não oferece empresa inativa como novo relacionamento.
- O seletor de criação de base do painel aceita somente tenants ativos.
- Empresas inativas continuam visíveis na listagem administrativa do Superuser, permitindo reativação sem perda de histórico.

## Validação

- `manage.py check`: aprovado.
- `makemigrations --check --dry-run`: nenhuma alteração detectada.
- Testes focados de onboarding, seções documentais, seletores, catálogo e isolamento tenant: 47 aprovados.
- Suíte completa: 613 testes aprovados em 735,780 segundos.

## Próximo incremento

Adicional G.7 — revisão final detalhada e ativação do tenant.
