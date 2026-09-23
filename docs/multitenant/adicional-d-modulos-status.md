# Adicional D — Módulos independentes (23/09/2026)

Foram adicionados quatro códigos técnicos independentes ao catálogo de módulos:

- `auditorias`;
- `documentacao`;
- `usuarios`;
- `cadastros`.

Auditorias não depende mais de Estoque. Documentação e Usuários possuem gates
próprios de menu e backend. Cadastros pode ser desligado mantendo as consultas
de Equipamentos e Insumos disponíveis; criação e edição exigem simultaneamente
o módulo funcional correspondente e `cadastros`.

O middleware aplica os gates a GET, POST, AJAX, downloads e demais métodos das
rotas mapeadas. O Superuser conserva o bypass de plataforma. Desabilitar um
módulo não remove nenhum dado.

## Provisionamento e compatibilidade

O onboarding oficial cria a empresa inativa. Nesse estado todos os registros de
`ModuloEmpresa` nascem desabilitados e somente a seleção explícita do Superuser
os habilita. A criação direta de uma empresa já ativa permanece como caminho
legado interno e conserva os módulos habilitados para não interromper fixtures,
integrações e rotinas anteriores ao onboarding.

A migration `0057_modulos_independentes` habilita os quatro novos módulos para
empresas que já existiam quando a migration foi executada. No banco local foram
preservadas cinco empresas, totalizando vinte configurações ativas e nenhuma
configuração nova desativada indevidamente. O reverse da carga é `noop` para não
apagar configurações do tenant em um rollback; o campo e os dados permanecem
compatíveis com o schema anterior.

## Validação

- 43 testes focados de features, menus, backend, onboarding e painel aprovados;
- 18 testes de enforcement aprovados, incluindo GET e POST;
- suíte completa: 591 testes aprovados;
- `python manage.py check`: aprovado;
- `python manage.py makemigrations --check --dry-run`: nenhuma alteração;
- migration `estoque.0057` aplicada no banco local;
- senhas e secrets não foram modificados;
- sem commit, push ou deploy.

O Adicional D está concluído. O próximo bloco previsto é o Adicional E —
Terminologia — e não foi iniciado nesta execução.
