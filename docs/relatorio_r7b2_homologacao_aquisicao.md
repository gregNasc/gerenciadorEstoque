# R7.B.2 — Interface de homologação e novas aquisições

**Data:** 28/10/2026  
**Branch:** `main`  
**Baseline implantado:** `458261980306b4bf2d5c360f7e2d3cc8a226275f`  
**Status:** aprovado localmente; não implantado

## Escopo realizado

- nova tela `Compras > Fornecedores homologados`;
- vínculo por empresa usando o CNPJ exato, sem listar o diretório global;
- fluxo visível `Pendente > Homologado > Suspenso/Inativo`;
- troca de status protegida pelo escopo do tenant;
- carregamento dinâmico dos fornecedores homologados após selecionar a empresa
  na nova Aquisição;
- validação do formulário e do serviço: fornecedor pendente, suspenso, inativo ou
  pertencente a outro tenant não pode ser usado;
- aquisições históricas permanecem acessíveis sem conversão de dados;
- separação entre permissão de catálogo operacional e permissão financeira de
  Aquisições.

## Experiência do usuário

O fluxo ficou explícito:

```text
Informar empresa e CNPJ
        ↓
Vínculo pendente
        ↓
Revisar e homologar
        ↓
Fornecedor aparece na nova Aquisição
```

Mensagens orientam quando o CNPJ não existe ou está inativo. Nesse caso, o
usuário deve solicitar ao Superuser o cadastro da identidade canônica. A tela
não apresenta nomes ou CNPJs vinculados exclusivamente a outro tenant.

## Segurança

- Admin/Compras acessam somente empresas autorizadas;
- API de fornecedores valida a empresa no servidor e retorna `404` para outro
  tenant;
- a lista do campo `fornecedor` é filtrada no servidor, além do JavaScript;
- `AquisicaoService.criar` repete a validação dentro da transação;
- alterar HTML ou enviar POST manual não contorna a homologação;
- `jose.barboza` não acessa Aquisições, preços ou homologações;
- Gestores continuam com cadastros operacionais, mas não recebem permissão
  financeira por meio da permissão de catálogo.

## Compatibilidade e dados existentes

- nenhuma Aquisição histórica foi alterada;
- nenhum fornecedor foi homologado automaticamente;
- não há migração de dados nesta subetapa;
- a única migration do conjunto R7.B continua sendo
  `compras.0005_fornecedorempresa`;
- depois do deploy, novas Aquisições exigirão homologação explícita, enquanto as
  antigas continuarão consultáveis normalmente.

## Arquivos principais

- `compras/forms.py`
- `compras/views.py`
- `compras/urls.py`
- `compras/services.py`
- `compras/policies.py`
- `estoque/policies/compras.py`
- `compras/templates/compras/fornecedores_empresa.html`
- `compras/templates/compras/aquisicao_form.html`
- `compras/templates/compras/aquisicao_lista.html`
- `compras/test_fornecedor_empresa_r7b.py`

## Testes

### R7.B completo

```text
10 / 10 aprovados em 2,512 s
```

Inclui:

- vínculo e homologação pela interface;
- diretório global não exposto;
- isolamento entre tenants na página e API;
- formulário exibindo somente homologados do tenant;
- fornecedor pendente bloqueado e homologado aceito;
- usuário financeiro restrito bloqueado;
- regras de unicidade e fornecedor canônico inativo.

### Regressão completa de Compras

```text
46 / 46 aprovados em 9,887 s
```

Após pequenos reforços de validação de identificadores, os 10 testes específicos
foram executados novamente e permaneceram aprovados.

### Checks

```text
python manage.py check
System check identified no issues.

python manage.py makemigrations --check --dry-run
No changes detected.

git diff --check
Sem erro; somente avisos informativos LF/CRLF.
```

Os testes usaram SQLite temporário e uma configuração transitória que removeu
somente `daphne` da inicialização, pois o avaliador automático de permissões do
ambiente atingiu o limite. O arquivo auxiliar e o banco temporário foram
removidos. Produção não foi acessada.

## Deploy e validação posterior

Deploy não executado. Quando autorizado:

1. backup normal;
2. publicar K.1, K.2 e R7.B juntos;
3. executar `python manage.py migrate`;
4. homologar explicitamente os fornecedores que cada empresa continuará usando;
5. testar uma nova Aquisição em tenant de homologação;
6. confirmar que outro tenant não vê o vínculo;
7. confirmar que `jose.barboza` recebe `403` nas telas financeiras;
8. confirmar que Aquisições antigas continuam disponíveis.

## Próxima subetapa proposta

R7.C — fundação de Cotações: múltiplos fornecedores homologados por solicitação,
comparação objetiva e decisão humana com justificativa, sem escolha automática
do menor preço.

**STOP — aguardando autorização.**
