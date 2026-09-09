# Ajuste — seleção multiempresa por Admin

Data do checkpoint: 2026-09-07.

## Objetivo

Permitir que cada Perfil Admin tenha uma seleção própria de empresas adicionais
dentro dos relacionamentos autorizados da sua Empresa principal.

Para um Admin da Inventory Brasil, as combinações suportadas são, por exemplo:

- somente Inventory Brasil;
- Inventory Brasil + Inventory LATAM;
- Inventory Brasil + OXXO;
- Inventory Brasil + Inventory LATAM + OXXO.

O relacionamento persistido define o limite máximo possível. A seleção do
Perfil define o subconjunto efetivamente acessível àquele usuário.

## Regra aplicada

O campo `Perfil.empresas_acesso_adicional` aceita somente destinos de
relacionamentos ativos, com ao menos uma capability ativa, cuja origem seja a
Empresa principal do Perfil.

- apenas o role Admin pode manter essa seleção;
- Gestor e Operador continuam vinculados às Bases e têm a seleção limpa;
- a Empresa principal nunca depende desse campo;
- não existe herança inversa: Admin LATAM e Admin OXXO continuam restritos à
  própria empresa, salvo relacionamento direcional configurado explicitamente;
- uma empresa sem relacionamento não pode ser incluída por manipulação do POST.

## Compatibilidade de dados

A migration `0046_perfil_empresas_acesso_adicional` preserva o acesso já
existente: cada Admin recebeu inicialmente os destinos que o relacionamento
ativo anterior já tornava acessíveis. A operação é idempotente e elimina
duplicações quando um relacionamento possui várias capabilities.

No banco local, o Admin de tenant já existente da Inventory Brasil permaneceu
com Inventory LATAM e OXXO selecionadas. A conta `admin` continua sendo o único
Superuser.

Nenhuma senha foi criada, redefinida ou regravada por este ajuste. Ao editar um
usuário sem preencher o campo de senha, o hash existente é preservado.

## Interface

A tela de cadastro e edição de usuários exibe “Empresas adicionais do Admin”.
As opções são filtradas pela Empresa principal e aparecem somente para o tipo
Admin. A listagem mostra as empresas adicionais de cada Perfil.

## Arquivos principais

- `estoque/models.py`;
- `estoque/tenant_context.py`;
- `estoque/tenant_scope.py`;
- `estoque/middleware.py`;
- `estoque/views.py`;
- `estoque/templates/estoque/cadastrar_usuarios.html`;
- `estoque/migrations/0046_perfil_empresas_acesso_adicional.py`;
- `estoque/test_admin_multi_company.py`.

