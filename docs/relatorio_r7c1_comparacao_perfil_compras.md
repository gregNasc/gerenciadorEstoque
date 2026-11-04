# R7.C.1 — Comparação moderna e permissões do perfil Compras

**Data:** 28/10/2026  
**Branch:** `main`  
**Baseline implantado:** `458261980306b4bf2d5c360f7e2d3cc8a226275f`  
**Status:** aprovado localmente; não implantado

## Escopo realizado

- remoção de `Comparar Gimba e Fidelity` da caixa de seleção individual;
- preservação de Gimba e Fidelity como fontes individuais quando habilitadas;
- conclusão do modo moderno `Comparar`, com seleção de duas ou mais fontes;
- processamento concorrente somente das fontes escolhidas;
- validação no servidor de fonte inválida, desabilitada ou comparação com menos
  de duas opções;
- manutenção do histórico agregado como `COMPARATIVO`, sem quebrar pesquisas
  antigas;
- inclusão explícita do perfil funcional Compras nos painéis de quantidade e
  saúde do estoque;
- teste consolidado das permissões de Compras em estoque, preços, pesquisa,
  aquisições e homologação de fornecedores.

## Fluxo da pesquisa

```text
Individual
    selecionar uma fonte
        ↓
    pesquisar

Comparar
    selecionar duas ou mais fontes
        ↓
    consultas concorrentes
        ↓
    quadro único de resultados
```

A comparação continua informativa. O sistema não escolhe automaticamente o
menor preço e mantém o aviso para conferir embalagem, unidade, frete e entrega.

## Perfil Compras

Com tenant e Bases explicitamente atribuídos, o tipo Compras pode acessar:

- Estoque de Insumos e respectivas quantidades;
- Saúde do Estoque de insumos, equipamentos e visão geral;
- Custos e preços unitários;
- Pesquisa e comparação de preços;
- Aquisições;
- homologações de fornecedores.

Todos os querysets continuam limitados às empresas e Bases autorizadas. Um
Operador comum não herda essas telas apenas por possuir o papel-base Operador.
Admin e Superuser permanecem autorizados; as regras já existentes de Financeiro
e Executivo não foram removidas nesta subetapa. `jose.barboza` continua sob o
bloqueio financeiro específico.

## Compatibilidade

- pesquisas históricas com fonte `COMPARATIVO` continuam legíveis;
- chamadas legadas do serviço ainda são aceitas internamente;
- somente a opção redundante foi removida da interface;
- nenhuma tabela ou dado existente foi alterado;
- nenhuma migration nova foi necessária.

## Arquivos principais

- `insumos/services/preco_online_service.py`
- `insumos/views/custos.py`
- `insumos/templates/insumos/custos/pesquisa_precos.html`
- `insumos/views/saude_estoque.py`
- `estoque/context_processors.py`
- `insumos/test_preco_fornecedores_online.py`
- `compras/test_perfil_compras_r7c.py`

## Testes

### Contrato específico

```text
13 / 13 aprovados em 5,330 s
```

Cobertura:

- opção legada ausente;
- comparação moderna processando Gimba e Fidelity selecionadas;
- compatibilidade da comparação legada no serviço;
- permissões completas do perfil Compras;
- bloqueio das telas especializadas para Operador comum.

### Regressão consolidada

```text
66 / 66 aprovados em 38,369 s
```

Incluiu toda a suíte de Compras, testes de custos e fornecedores online.

### Checks

```text
python manage.py check
System check identified no issues.

python manage.py makemigrations --check --dry-run
No changes detected.

git diff --check
Sem erro; somente avisos informativos LF/CRLF.
```

Os testes foram executados em SQLite temporário com `daphne` removido apenas da
configuração transitória de testes. Os arquivos auxiliares foram excluídos e
nenhum banco operacional foi acessado.

## Próxima subetapa proposta

R7.C.2 — modelo persistente de Cotação ligado à Solicitação, com múltiplos
fornecedores homologados, prazo, frete, impostos, desconto, condição de
pagamento, validade da proposta e justificativa da decisão humana.

**STOP — aguardando autorização.**
