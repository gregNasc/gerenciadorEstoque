# R2.M — Interface operacional de Custódia

## Objetivo

Disponibilizar o fluxo operacional que faltava à R2 sem depender do Django
Admin. A interface liga `Colaborador`, `Custodia`, `ItemCustodia`, termos e
devoluções aos equipamentos e linhas móveis já existentes.

## Regras de acesso

- Superuser pode consultar e administrar;
- Admin do tenant pode consultar e administrar empresas presentes no seu
  `manageable_company_ids`;
- `jose.barboza` pode consultar quando possuir perfil Admin, mas nunca criar ou
  alterar Colaboradores, Custódias ou vínculos;
- Gestor e Operador não acessam o módulo;
- empresas inativas não aparecem;
- objetos de outro tenant retornam acesso negado ou 404.

## Colaboradores

Um Colaborador representa uma pessoa real e pode:

- estar vinculado opcionalmente a um `User` ativo da mesma empresa; ou
- existir sem conta de acesso ao sistema.

Ao selecionar um usuário, nome e e-mail são preenchidos a partir da conta
quando não forem informados no formulário. O vínculo continua opcional e
One-to-One.

## Fluxo de Custódia

1. cadastrar ou selecionar o Colaborador;
2. selecionar empresa e Base dentro do escopo de gestão do Admin;
3. escolher um ou mais equipamentos e/ou linhas móveis elegíveis;
4. ativar a Custódia;
5. sincronizar o campo legado `Equipamento.responsavel`;
6. gerar o Termo de Entrega em armazenamento privado;
7. registrar devolução total ou com item faltante;
8. gerar Termo de Devolução separado e liberar os itens devolvidos.

Ativos já presentes em outra Custódia vigente não aparecem como disponíveis e
continuam protegidos pelas constraints do banco.

## Interface

O dropdown **Custódia** da navegação contém:

- Custódias;
- Colaboradores;
- Nova Custódia, para quem pode gerenciar;
- Novo colaborador, para quem pode gerenciar.

A edição do equipamento mostra a Custódia vigente ou, quando disponível, o
atalho **Vincular a colaborador**.

## Validação

- `python manage.py check`: aprovado, sem alertas;
- `python manage.py makemigrations --check --dry-run`: nenhuma alteração;
- testes específicos: `estoque.test_custodia_ui_r2m`;
- regressão acumulada R2.A–R2.M: 118 testes aprovados;
- regressão completa do projeto: 822 testes aprovados;
- `git diff --check`: aprovado (somente avisos de normalização LF/CRLF);
- catálogo espanhol atualizado e `django.mo` compilado com validação de formato;
- nenhuma migration nova: os modelos da R2 já existiam.

## Deploy

Mudança de aplicação, sem alteração de schema. Após publicar:

1. confirmar o dropdown com Superuser e Admin;
2. confirmar ausência do dropdown para Gestor e Operador;
3. confirmar que José não vê ações de criação/alteração;
4. cadastrar um Colaborador de teste;
5. criar uma Custódia controlada com um equipamento elegível;
6. baixar o Termo de Entrega;
7. registrar a devolução e baixar o Termo de Devolução;
8. confirmar que o equipamento voltou a ficar disponível.
