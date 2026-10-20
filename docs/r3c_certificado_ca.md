# R3.C — Certificado de Aprovação (CA)

## Regra consolidada

O CA pertence ao produto EPI do fabricante/importador. Tamanho e outras
variações pertencem a `VarianteEpi`; por isso, não se cria uma cópia do CA para
cada tamanho.

```text
Produto EPI
├── Certificado(s) CA
├── Variante P
├── Variante M
├── Variante G
└── Lotes físicos por Base
```

## Implementação

- `CertificadoEpiService.registrar()` normaliza o número do CA e reutiliza o
  certificado já cadastrado no mesmo produto.
- Um número de CA não pode ser associado silenciosamente a outro produto. A
  operação orienta cadastrar tamanhos como variantes do produto existente.
- Número vazio é rejeitado no serviço, no modelo e por restrição no banco.
- A validade do CA permanece em `CertificadoEpi.validade_ca`.
- A validade física permanece em `LoteEpi.validade_fisica`; alterar uma não
  modifica a outra.

## Banco e compatibilidade

A migration `insumos/migrations/0041_certificadoepi_epi_ca_numero_nao_vazio.py`
adiciona somente a restrição que impede CA vazio. A estrutura criada na R3.B é
preservada e nenhum dado existente é removido.

## Validação

Os testes da R3.C cobrem normalização e reutilização do CA, compartilhamento
entre variantes, rejeição de duplicação em outro produto, número vazio e
independência entre validade documental e física.

- 5 testes específicos da R3.C aprovados;
- 132 testes integrados de Catálogo, Custódia e `insumos` aprovados;
- `manage.py check` sem problemas;
- nenhuma alteração de migration pendente.

Alertas de vencimento e estados operacionais pertencem à R3.D e não foram
iniciados.
