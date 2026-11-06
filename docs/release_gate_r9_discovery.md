# Release gate R9 — descoberta da integração TOTVS

Status: **FUNDAÇÃO PRONTA; CONECTOR ESPECÍFICO BLOQUEADO**
Motivo do bloqueio restante: produto, versão, módulos, contrato de API e ambiente
de homologação ainda não foram informados.

Este gate evita assumir Protheus ou qualquer outro produto TOTVS e impede que
campos, identificadores ou regras específicas do ERP vazem para o domínio do
Gerenciador de Estoque.

## Resultado da auditoria local

- Não existe cliente, mapper, endpoint, credencial ou modelo específico de TOTVS.
- Não há segredo TOTVS versionado no repositório.
- O aplicativo `integracao` já separa clientes, mapeadores, serviços e registros
  de execução para outras integrações; o R9 deve manter essa arquitetura.
- O fluxo interno de Compras já possui cotação, proposta escolhida, aquisição,
  itens, pedido de compra, centro de custo, NF-e, recebimento e divergências.
- O Gerenciador deve continuar sendo a fonte do fluxo operacional interno até
  que a responsabilidade de cada sistema seja formalmente definida.
- Nenhum código deve escrever diretamente no banco de dados do ERP.

## Fundação implementada sem assumir produto

- Configuração independente por empresa, desativada por padrão.
- Chave geral `TOTVS_ENABLED=False` e bloqueio separado para produção.
- Contrato de adaptador e registro por produto TOTVS.
- Fila auditável com chave de idempotência determinística.
- Histórico de tentativas sem persistir payloads, preços ou credenciais.
- Estados para envio, confirmação, nova tentativa, falha e reconciliação.
- Backoff exponencial limitado e timeout configurável para o futuro cliente.
- Resultado ambíguo nunca é reenviado automaticamente.
- Comando `python manage.py check_totvs_readiness` sem acesso à rede.

Variáveis já aceitas, todas seguras e desativadas por padrão:

```text
TOTVS_ENABLED=False
TOTVS_ALLOW_PRODUCTION=False
TOTVS_TIMEOUT=20
TOTVS_MAX_RETRIES=3
TOTVS_RETRY_BASE_SECONDS=60
```

Nenhuma variável de credencial foi inventada. Elas dependerão do método oficial
de autenticação do produto e da versão que forem confirmados.

## Informações obrigatórias antes do conector

| Tema | Resposta necessária |
| --- | --- |
| Produto | Nome exato do produto TOTVS; não assumir Protheus |
| Versão | Versão/release instalada e política de atualização |
| Módulos | Módulos de Compras, Estoque, Fiscal e Financeiro efetivamente usados |
| Processo atual | Passo a passo real executado por Compras e Financeiro |
| Direção dos dados | O que o Gerenciador envia, recebe ou apenas consulta |
| Gatilho inicial | Evento interno que cria ou atualiza o registro remoto |
| API | Documentação oficial, base URL e endpoints suportados |
| Autenticação | Tipo de autenticação e duração/renovação do token |
| Homologação | Ambiente, empresa/filial de teste e dados seguros para validação |
| Identificadores | Empresa, filial, fornecedor, produto, centro de custo e unidade |
| Campos obrigatórios | Campos exigidos em cada operação remota |
| Status | Estados remotos e correspondência com os estados locais |
| Responsabilidades | Sistema responsável por aprovar, cancelar e corrigir cada etapa |
| Reconciliação | Como consultar o resultado e reparar divergências |
| Volume | Quantidade esperada, limites de API e janelas de processamento |

## Fluxos internos candidatos ao mapeamento

Estes são pontos de análise, não integrações já autorizadas:

1. `ProcessoCotacao` e `CotacaoFornecedor`: decisão de compra e fornecedor.
2. `Aquisicao`: pedido aprovado, empresa, Base, fornecedor, centro de custo e
   número do pedido.
3. Itens da aquisição: códigos internos, quantidades, unidade e valores.
4. `NotaFiscalAquisicao`: chave, emitente, valores e itens fiscais.
5. Recebimento e divergências: quantidades recebidas e diferenças encontradas.

O primeiro fluxo remoto só será escolhido após a confirmação do processo real.

## Contrato arquitetural obrigatório

```text
domínio interno
    ↓
serviço de integração
    ↓
mapper TOTVS específico do produto/versão
    ↓
cliente de API suportada pela TOTVS
```

- IDs e nomes de campos do ERP ficam somente em `integracao/`.
- Credenciais ficam somente em variáveis secretas do ambiente.
- Payloads e logs nunca devem expor tokens, senhas ou dados financeiros a
  usuários sem permissão de Compras/Financeiro.
- `jose.barboza` não pode receber valores financeiros ou preços pela integração.
- Cada envio deve possuir chave de idempotência, timeout explícito e estado
  local independente do estado remoto.
- Falhas não podem apagar ou reverter silenciosamente dados internos.
- Retry automático só pode ocorrer quando a operação for comprovadamente segura.
- Operações ambíguas devem ser reconciliadas por consulta antes de novo envio.

## Gate técnico para homologação

- [ ] Produto, versão e módulos confirmados.
- [ ] Processo atual documentado e aprovado por Compras e Financeiro.
- [ ] Responsabilidade de cada sistema definida.
- [ ] Documentação oficial da API recebida.
- [ ] Autenticação e rotação de segredo definidas.
- [ ] Ambiente de homologação disponível.
- [ ] Mapeamento de empresa/filial e centros de custo validado.
- [ ] Mapeamento de fornecedores, produtos e unidades validado.
- [ ] Status local x remoto aprovado.
- [ ] Estratégia de idempotência e reconciliação aprovada.
- [ ] Timeouts, retries e limites de API definidos.
- [ ] Logs sem dados sensíveis e trilha de auditoria testados.
- [ ] Testes de contrato e cenários de falha aprovados.
- [ ] Plano de rollback sem perda de dados aprovado.

## Próximo passo autorizado

Após o preenchimento das informações obrigatórias, iniciar pelo menor fluxo de
homologação de ponta a ponta. O conector deve permanecer desativado por padrão
até os testes de contrato, idempotência, timeout, reconciliação e isolamento por
empresa serem aprovados.
