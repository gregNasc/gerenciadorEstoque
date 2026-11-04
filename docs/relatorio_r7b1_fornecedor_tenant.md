# R7.B.1 — Relação e homologação de fornecedor por tenant

**Data:** 28/10/2026  
**Branch:** `main`  
**Baseline implantado:** `458261980306b4bf2d5c360f7e2d3cc8a226275f`  
**Status:** aprovado localmente; não implantado

## Escopo realizado

- preservação de `FornecedorInsumo` como identidade jurídica canônica global;
- criação de `FornecedorEmpresa` como relação privada por tenant;
- estados explícitos `PENDENTE`, `HOMOLOGADO`, `SUSPENSO` e `INATIVO`;
- unicidade de um relacionamento por `empresa + fornecedor`;
- auditoria de cadastrador, homologador e data da homologação;
- serviço transacional para registrar e alterar o estado;
- consultas sempre limitadas às empresas autorizadas pela policy de Compras;
- inspeção pelo Django Admin para suporte de plataforma.

Esta subetapa não altera aquisições existentes e ainda não filtra o campo de
fornecedor na tela de Aquisição. A integração com a seleção e a interface de
homologação será feita somente na próxima subetapa, depois desta fundação estar
implantada e validada.

## Regra de segurança

```text
FornecedorInsumo
    identidade canônica global, editável somente por Superuser

FornecedorEmpresa
    relação/homologação visível apenas ao tenant autorizado
```

- Admin e grupo Compras podem administrar relações somente em empresas de seu
  escopo;
- um Admin não consulta nem altera a homologação de outro tenant;
- `jose.barboza` continua bloqueado nesta área financeira/comercial;
- a inspeção técnica pelo Django Admin é exclusiva de Superuser;
- a relação não armazena preço, valor, custo ou condição de pagamento;
- fornecedor canônico inativo não aparece na consulta de homologados ativos.
- fornecedor canônico inativo não pode ser homologado.

## Compatibilidade

- nenhuma linha existente foi convertida ou excluída;
- `Aquisicao.fornecedor` permanece apontando para o cadastro canônico;
- aquisições antigas e o fluxo atual continuam operando sem exigir relação
  retroativa;
- não há liberação automática de fornecedor global para empresa alguma.

## Arquivos desta subetapa

- `compras/models.py`
- `compras/migrations/0005_fornecedorempresa.py`
- `compras/services.py`
- `compras/admin.py`
- `estoque/policies/compras.py`
- `compras/test_fornecedor_empresa_r7b.py`
- `docs/relatorio_r7b1_fornecedor_tenant.md`

## Migration

`compras.0005_fornecedorempresa` cria somente uma tabela, seus relacionamentos,
índice por `empresa + status` e restrição única por `empresa + fornecedor`.
Não há migração de dados nem alteração em tabelas operacionais existentes.

## Testes executados

### Contrato específico R7.B.1

```text
6 / 6 aprovados
```

Cobertura:

- um fornecedor canônico com homologações independentes em duas empresas;
- isolamento de leitura e escrita entre tenants;
- bloqueio do usuário financeiro restrito;
- registro idempotente e unicidade no banco;
- ausência de campos financeiros no novo relacionamento.
- bloqueio da homologação de fornecedor canônico inativo.

### Suíte completa de Compras

```text
42 / 42 aprovados em 7,979 s
```

### Checks

```text
python manage.py check
System check identified no issues.

python manage.py makemigrations --check --dry-run
No changes detected.

git diff --check
Sem erro; apenas avisos informativos de conversão LF/CRLF.
```

Os testes usaram banco SQLite temporário e descartável porque o sandbox desta
sessão bloqueava o socket local criado pelo Daphne. Nenhum banco operacional foi
alterado.

## Deploy e validação posterior

Deploy não executado. Quando autorizado e depois de backup normal:

1. publicar o código;
2. executar `python manage.py migrate`;
3. confirmar `compras.0005_fornecedorempresa` como aplicada;
4. cadastrar uma relação pendente em tenant de homologação;
5. confirmar que outro tenant não enxerga essa relação;
6. confirmar que aquisições antigas continuam acessíveis.

## Próxima subetapa proposta

R7.B.2 — interface simples de homologação por empresa e uso somente dos
fornecedores homologados em novas aquisições, com estratégia explícita para os
fornecedores já usados no histórico.

**STOP — aguardando autorização.**
