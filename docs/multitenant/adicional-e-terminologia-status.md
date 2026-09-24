# Adicional E — Terminologia tenant-aware (23/09/2026)

O `TenantTerminologyService` passou a resolver, em uma única consulta por tipo,
os termos gerais no singular/plural e os nomes de apresentação dos módulos de
cada empresa. O contexto é memorizado no próprio request e disponibiliza:

- `tenant_labels`;
- `tenant_module_labels`;
- `tenant_dashboard_label`.

O código técnico permanece estável. URLs, models, permissions, services e
valores internos como `sick`, `equipamentos`, `base` e `regional` não foram
renomeados. Somente a apresentação ao usuário utiliza os rótulos do tenant.

## Superfícies atualizadas

Os rótulos tenant-aware foram aplicados à navegação principal, Dashboard de
Ativos, consulta e cadastro de equipamentos, gestão de usuários, fluxo SICK,
histórico, solicitações e transferências, chamados e telas centrais de
auditorias. Textos embutidos em JavaScript usam escape próprio antes de entrar
em mensagens e componentes dinâmicos.

Sem personalização, a interface conserva os nomes padrão da plataforma. Nomes
históricos gravados em caixa alta no catálogo técnico não alteram o fallback
visual. Com personalização, por exemplo, a mesma implementação interna pode
apresentar:

```text
sick          → Manutenção / Oficina
equipamento   → Máquina / Ativo
base          → Unidade
regional      → Setor
```

## Isolamento e validação

Os testes dedicados cobrem duas empresas com terminologias diferentes, ausência
de herança entre tenants, fallback seguro para valores vazios e cache por
request sem consultas repetidas. A empresa Alpha usa Máquinas, Unidades,
Setores e Manutenção; a empresa Beta usa Ativos e Oficina.

- 4 testes dedicados de terminologia aprovados;
- 6 testes focados de compatibilidade e isolamento aprovados;
- suíte completa: 595 testes aprovados;
- `python manage.py check`: aprovado;
- `python manage.py makemigrations --check --dry-run`: nenhuma alteração.

Senhas e Secret Key não foram modificadas. Não houve commit, push ou deploy.

O Adicional E está concluído. O próximo bloco previsto é o Adicional F —
Documentação — e não foi iniciado nesta execução.
