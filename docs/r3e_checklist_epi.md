# R3.E — Checklist e metadados de EPI

O fluxo de preenchimento do Checklist foi preservado. A assinatura pública de
`ChecklistService.adicionar_item` não mudou e itens comuns continuam funcionando
sem conhecimento da modelagem de EPI.

Quando o item é um EPI, o serviço grava em `ItemChecklist.metadados_epi_snapshot`
um retrato dos dados válidos naquele momento: produto, certificados CA,
variante/tamanho, lote da Base do inventário e estados de alerta. Lotes de outras
Bases não entram no snapshot.

O snapshot é histórico e deliberadamente não muda quando um CA ou lote é editado
depois do preenchimento. Registros legados podem permanecer com o JSON vazio.

Validações automatizadas cobrem:

- compatibilidade do fluxo atual;
- isolamento por Base/tenant;
- ausência de metadados em item comum;
- imutabilidade do histórico;
- criação direta de registros legados.
