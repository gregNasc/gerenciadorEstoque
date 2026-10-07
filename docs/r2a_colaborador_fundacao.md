# R2.A — Fundação de Colaborador

## Estado

Subetapa concluída localmente em 07/10/2026.

## Escopo entregue

- entidade `Colaborador` separada de `User`;
- colaborador pode existir sem conta de autenticação;
- associação opcional e exclusiva com um `User`;
- empresa obrigatória e Base opcional;
- nome, e-mail, telefone, matrícula, cargo/função, setor e estado ativo;
- matrícula única dentro da empresa quando informada;
- validação de Base e usuário contra vínculo entre tenants;
- policy de queryset com escopos distintos de visualização e gestão;
- normalização dos campos textuais antes da persistência.

## Migration

`estoque.0063_colaborador`

A migration é aditiva: cria uma tabela nova e não altera nem remove dados
existentes.

## Limite desta subetapa

Ainda não foram criados:

- telas ou endpoints de Colaborador;
- Local Físico;
- Custódia e seus itens;
- termos de entrega/devolução;
- integração DocuSign;
- notificações da R2.

O nome livre de responsável da R1 permanece intacto. Sua eventual adoção
da entidade `Colaborador` deve ocorrer em etapa posterior, com compatibilidade
e migration de dados explicitamente avaliadas.

## Validação

- testes direcionados R2.A: 7/7;
- R2.A + regressões centrais multi-tenant: 36/36;
- `python manage.py check`: aprovado;
- `git diff --check`: aprovado.

## STOP

Não houve commit, push, migration no banco local/produção ou deploy.
Não iniciar R2.B sem autorização.
