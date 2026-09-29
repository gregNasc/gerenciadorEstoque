# Adicional G.4 — Categorias no onboarding (27/09/2026)

A etapa de Categorias do onboarding permite ao Superuser:

- criar categorias próprias, uma por linha;
- renomear categorias já registradas;
- definir a ordem de apresentação;
- ativar ou desativar categorias sem apagar dados;
- avançar com zero categorias, quando isso for válido para o tenant.

O backend consulta e altera somente categorias cuja `empresa` é o tenant atual.
IDs enviados manualmente para categorias de outra empresa são ignorados. Nomes
duplicados, inclusive com diferença apenas de maiúsculas/minúsculas, tamanhos
inválidos e ordens fora do intervalo impedem toda a gravação, sem alterações
parciais.

Nenhuma categoria histórica ou pertencente a outro tenant é copiada durante o
onboarding.
