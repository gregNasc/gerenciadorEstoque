# R3.A — Natureza e forma de controle de Insumos

## Objetivo

Separar duas características que estavam misturadas no campo legado
`Insumo.tipo_controle`:

- **natureza**: Consumível, EPI ou Reutilizável;
- **forma de controle**: Quantidade, Lote ou Individualizado.

Esta subetapa não implementa CA, fabricante, variantes, lotes físicos ou
validade. Esses dados pertencem às próximas subetapas da R3.

## Compatibilidade

O campo `tipo_controle` foi mantido no banco e não tem seus valores alterados
pela migration. Os fluxos antigos continuam encontrando `QUANTIDADE`, `LOTE`
ou `REUTILIZAVEL` como antes.

A migration `0039_separar_natureza_forma_controle` adiciona os novos campos e
classifica os registros existentes assim:

| Situação legada | Natureza | Forma de controle |
|---|---|---|
| Categoria `EPI` | EPI | Quantidade, salvo lote explícito |
| `tipo_controle=REUTILIZAVEL` fora de EPI | Reutilizável | Quantidade |
| `tipo_controle=LOTE` | Consumível | Lote |
| Demais registros | Consumível | Quantidade |

A detecção da categoria EPI ignora maiúsculas, minúsculas e espaços nas
extremidades. Como o campo legado não é reescrito, o rollback de schema não
perde sua classificação anterior.

## Proteções

- defaults compatíveis com o comportamento existente;
- constraints impedem naturezas e formas de controle desconhecidas;
- índices permitem filtros futuros de EPI e controle sem varrer todo o
  catálogo;
- o formulário de edição passa a apresentar os dois conceitos separados;
- a carga inicial mantém os campos novos coerentes sem remover o legado;
- Estoque e Checklist continuam usando as estruturas atuais nesta subetapa.

## Validação

- 5 testes direcionados da R3.A aprovados;
- 62 testes do app `insumos` aprovados, incluindo Estoque e Checklist;
- `python manage.py check`: aprovado, sem alertas;
- `python manage.py makemigrations --check --dry-run`: nenhuma alteração;
- catálogo espanhol atualizado e compilado;
- nenhuma chamada a banco ou serviço de produção.

## Deploy futuro

1. gerar backup do banco;
2. publicar o código;
3. executar `python manage.py migrate`;
4. conferir a quantidade de Insumos por natureza e forma de controle;
5. validar a listagem e a edição de um Consumível, um EPI e um Reutilizável;
6. validar uma entrada de Estoque e um Checklist existente.

Não há remoção ou renomeação de coluna nesta migration.
