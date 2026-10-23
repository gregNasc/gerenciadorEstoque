# R4.C — Celulares e IMEI opcional

## Entrega

Foi adicionada a capacidade tenant-aware `POSSUI_IMEI`. O administrador pode
marcar no catálogo quais produtos aceitam os campos `IMEI 1` e `IMEI 2`, sem
depender do nome "Celular" ou de uma categoria fixa.

Os dois IMEIs são opcionais. Quando informados:

- devem possuir exatamente 15 dígitos numéricos;
- devem ser diferentes entre si;
- não podem repetir um IMEI já usado em nenhum dos dois slots de outro ativo.

Produtos sem a capacidade não exibem os campos e rejeitam novos IMEIs. Valores
legados continuam preservados em edições não relacionadas.

## Banco de dados

A migração `estoque.0073_equipamento_imeis` adiciona duas colunas anuláveis e
únicas. Ela não altera registros existentes.

## Validação

- verificação Django: aprovada;
- migrations: nenhuma alteração pendente;
- 55 testes de capacidades, equipamentos, linhas móveis e Custódia: aprovados.

O deploy continua pendente de autorização explícita e deve executar
`python manage.py migrate`.
