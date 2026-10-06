# R1.0 — Contrato técnico de Chips / Linhas Móveis

## Status

Concluído em 29/09/2026.

Esta é a primeira subetapa da Release R1. Ela fixa as regras de domínio e de
segurança antes da criação de models, migrations, services ou telas.

## Baseline

- branch: `main`;
- commit validado: `7e48d9e5702ae3f35b5dd67abd442f41b34bc0f3`;
- `HEAD` e `origin/main` apontam para o mesmo commit;
- worktree limpa no início desta subetapa;
- baseline funcional: Adicional J, 632 testes aprovados;
- não há domínio de linha móvel, ICCID, PIN ou PUK no código atual.

## Limite da R1

A R1 cria somente o domínio de Chips / Linhas Móveis e sua integração com
`Equipamento`. Não inicia Custódia, Colaborador, EPI, Solicitações ou Compras.

Linhas Móveis serão uma capacidade do módulo `EQUIPAMENTOS`, não um módulo
independente nesta release. A ausência da capacidade no catálogo do tenant
mantém campos, ações e consultas de conectividade indisponíveis.

Uma separação futura em módulo próprio somente poderá ocorrer por requisito
explícito e migration compatível.

## Elegibilidade sem hardcode

É proibido decidir elegibilidade com comparações como:

```python
categoria == "Coletor"
descricao == "Coletor"
```

A R1 deve introduzir uma capacidade extensível associada ao catálogo do
produto no tenant. O primeiro código será:

```text
CONECTIVIDADE_MOVEL
```

A capacidade será resolvida no contexto de `CatalogoProdutoEmpresa`, pois o
mesmo produto técnico pode possuir configuração diferente em cada tenant.
Esse mecanismo poderá ser ampliado pela R4 sem migrar regras textuais.

## Entidades previstas

### Operadora móvel

`OperadoraMovel` será tenant-aware e administrável, evitando hardcode
permanente. Campos mínimos:

```text
empresa
nome
codigo
ativa
criado_em
atualizado_em
```

Vivo, TIM e Claro poderão ser configuradas para os tenants que utilizarem a
funcionalidade. Não haverá fallback global permissivo.

### Linha móvel

`LinhaMovel` representará a unidade controlada pelo tenant:

```text
empresa
base de guarda/localização
número normalizado
operadora
ICCID
status
observação
datas relevantes
criado_por
criado_em
atualizado_em
```

A Base é obrigatória enquanto a linha estiver disponível. Durante vínculo
ativo, a Base da linha deve corresponder à Base atual do equipamento.

O número será armazenado em formato normalizado compatível com E.164 e
apresentado no padrão local quando for brasileiro. Formatação visual nunca
participará de unicidade ou autorização.

### Credenciais sensíveis

PIN, PIN 2, PUK e PUK 2 não ficarão em colunas textuais comuns de
`LinhaMovel`. Serão isolados em uma estrutura de credenciais com conteúdo
criptografado e acesso exclusivo por service autorizado.

Regras obrigatórias:

- chave independente de `SECRET_KEY`;
- chave fornecida por variável de ambiente/secret;
- nenhuma credencial em logs, exceptions, histórico, Tory ou exports;
- leitura mascarada por padrão;
- descriptografia somente com permissão específica;
- ausência da chave falha fechada para escrita/leitura de credenciais, sem
  impedir o uso de linhas que não possuam PIN/PUK cadastrado;
- rotação de chave deve possuir procedimento documentado antes do Release
  Gate.

Nenhum secret será criado ou alterado automaticamente pelo desenvolvimento.

### Vínculo temporal

`VinculoLinhaEquipamento` será histórico, nunca uma relação `OneToOne`
permanente:

```text
linha
equipamento
inicio_em
fim_em
motivo_fim
vinculado_por
desvinculado_por
criado_em
```

Um vínculo é ativo quando `fim_em` está vazio.

### Histórico da linha

`HistoricoLinhaMovel` registrará eventos próprios da linha, inclusive quando
ela não estiver vinculada a equipamento:

```text
CADASTRO
ALTERACAO
ATIVACAO
INATIVACAO
VINCULO
DESVINCULO
TROCA
```

O histórico deve guardar tenant, autor, data e metadados não sensíveis. O
`Historico` atual do equipamento poderá receber um evento correspondente para
preservar a linha do tempo do equipamento, sem duplicar PIN/PUK.

## Invariantes de banco e domínio

- número normalizado único dentro da empresa;
- ICCID único dentro da empresa quando informado;
- no máximo um vínculo ativo por linha;
- no máximo uma linha ativa por equipamento;
- `fim_em` não pode ser anterior a `inicio_em`;
- linha, Base e equipamento devem pertencer à mesma empresa;
- produto do equipamento precisa possuir `CONECTIVIDADE_MOVEL` ativa no
  catálogo daquela empresa;
- models históricos usam `PROTECT` quando a exclusão destruiria auditoria;
- troca, vínculo e desvínculo são operações atômicas;
- validação em service e model complementa constraints do PostgreSQL;
- mensagens de conflito não podem revelar linha ou ICCID de outro tenant.

## Status e transições

Estados iniciais previstos:

```text
DISPONIVEL
EM_USO
SUSPENSA
INATIVA
```

Regras:

- linha vinculada fica `EM_USO`;
- desvinculação válida retorna a `DISPONIVEL`, salvo inativação explícita;
- linha `SUSPENSA` ou `INATIVA` não pode iniciar vínculo;
- inativação encerra previamente qualquer vínculo ativo em uma única
  transação, com motivo obrigatório;
- reativação não restaura vínculo antigo automaticamente.

## Transferências

Transferência de Base dentro da mesma empresa pode mover a Base da linha junto
com o equipamento, registrando histórico.

Transferência entre empresas será bloqueada enquanto existir linha ativa. A
linha deve ser desvinculada explicitamente antes da transferência. A
propriedade da linha nunca muda automaticamente entre tenants.

## Permissões e escopo

Permissões previstas:

```text
visualizar_linhas_moveis
gerenciar_linhas_moveis
vincular_linhas_moveis
visualizar_credenciais_linhas_moveis
```

Comportamento padrão:

- Superuser: plataforma, sujeito a ações explícitas;
- Admin: empresa principal e empresas adicionais explicitamente autorizadas;
- Gestor: somente Bases de seu perfil; pode vincular/desvincular quando tiver
  a permissão funcional;
- Operador: somente visualização da linha atual de equipamento acessível,
  quando autorizado; nunca vê PIN/PUK por papel implícito;
- credenciais exigem permissão dedicada, mesmo para Admin;
- relacionamentos entre empresas só ampliam escopo quando a capability
  correspondente estiver explicitamente configurada.

Querysets, forms, views, APIs, downloads e Tory devem partir da mesma policy.

## Regra financeira de José Barboza

Linhas móveis não contêm preço nesta release. Qualquer inclusão futura da
seção em ficha completa deve continuar usando `ComprasAccessPolicy` para
ocultar custos, documentos fiscais e históricos financeiros de usuários
restritos. A seção de conectividade não pode servir de atalho para dados de
Compras.

## Interface prevista

- Cadastro de equipamento: vínculo opcional somente quando o produto tiver a
  capacidade `CONECTIVIDADE_MOVEL`;
- Edição: consultar linha atual, vincular, trocar e desvincular;
- Ficha/modal: seção reutilizável `Conectividade`;
- listagens comuns: telefone mascarado/conforme permissão, sem PIN/PUK;
- troca nunca sobrescreve o vínculo anterior;
- Coletor sem linha continua válido.

## APIs, exports, Tory e notificações

- endpoints sempre filtram tenant e Base antes de resolver IDs;
- serializers comuns não incluem credenciais;
- exports comuns não incluem PIN/PUK;
- não haverá export de credenciais na R1;
- Tory pode informar linha atual e operadora somente conforme policy;
- Tory nunca recebe PIN/PUK em contexto ou resposta;
- notificações usam destinatários calculados pelo tenant e não incluem
  credenciais;
- jobs devem falhar fechados quando o tenant estiver inativo.

## Compatibilidade e migrations

- migrations serão aditivas;
- nenhum campo atual de `Equipamento` será removido;
- `responsavel`, SICK, transferências e históricos atuais permanecem
  compatíveis;
- não haverá data migration baseada no texto `Coletor`;
- a capacidade será configurada explicitamente por tenant;
- migration de dados, se necessária para o Grupo Inventory, exigirá seleção
  explícita e estratégia de reversão/preservação documentada.

## Sequência aprovada da R1

1. **R1.A — fundação de dados e capacidade**;
2. **R1.B — policy, criptografia e services**;
3. **R1.C — cadastro de linha e operadoras**;
4. **R1.D — vínculo no cadastro do equipamento**;
5. **R1.E — edição, troca, desvínculo e transferências**;
6. **R1.F — ficha/modal e histórico**;
7. **R1.G — auditoria de APIs, exports, Tory e notificações**;
8. **R1.H — Release Gate**.

Cada subetapa termina com testes e STOP. Nenhuma estrutura de R2 será criada
durante a R1.

## Próxima subetapa

R1.A deverá criar somente a fundação de dados e as constraints aditivas, com
testes de models, isolamento e reversibilidade. Não deverá criar telas nem
ativar a funcionalidade em produção.
