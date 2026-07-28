# Tory e Portal de inventários em tempo real

## Objetivo

Permitir que a Tory consulte, em modo somente leitura, a tela autenticada de
inventários em tempo real do Portal Inventory Brasil. A integração não depende
do repositório local `InventoryPortal-master` e não executa alterações no Portal.

## Fluxo

1. A pergunta é interpretada por regras locais e, opcionalmente, por um LLM.
2. O resultado é reduzido a filtros estruturados: período, cliente, loja,
   status e métricas.
3. O Django valida período e escopo de acesso.
4. Uma conta técnica autentica no Portal com CSRF e sessão HTTPS.
5. A listagem é consultada pelo período solicitado.
6. Quando a pergunta exige métricas, o detalhe de cada inventário é aberto.
7. A Tory consolida os dados e identifica o Portal e o horário da consulta.

O LLM não recebe usuário/senha, cookies, HTML, respostas do Portal nem acesso
direto ao cliente HTTP. Ele não decide permissões e não executa ferramentas.

## Perguntas suportadas

- inventários em andamento, agora, neste ou nesse momento;
- inventários finalizados, agendados ou em preparação;
- filtro por sigla do cliente, número da loja, data ou período;
- progresso geral, loja e depósito;
- total de peças/itens e produtos contados;
- quantidade de pessoas e produtividade;
- início, fim, duração e última atualização;
- acuracidade geral, loja e depósito;
- preparação do piso de venda e depósito;
- progresso por seção;
- itens com maior valor ou quantidade;
- divergências e resumo de divergências;
- conferentes;
- conexão, tipo, liderança, regional e endereço;
- séries de produtividade e avanço disponibilizadas pelo Portal.

Consultas detalhadas com vários inventários são limitadas por
`INVENTORY_PORTAL_MAX_DETAIL_RECORDS`. A listagem e o período também têm limites
para não sobrecarregar o sistema de origem.

## Configuração

```dotenv
INVENTORY_PORTAL_ENABLED=True
INVENTORY_PORTAL_URL=https://novoportal.inventorybrasil.com.br/
INVENTORY_PORTAL_USERNAME=conta_tecnica
INVENTORY_PORTAL_PASSWORD=segredo
INVENTORY_PORTAL_TIMEOUT=20
INVENTORY_PORTAL_MAX_RANGE_DAYS=31
INVENTORY_PORTAL_MAX_DETAIL_RECORDS=20
```

A interpretação semântica é independente e permanece desligada por padrão:

```dotenv
TORY_LLM_ENABLED=True
TORY_LLM_MODEL=gpt-5.6-sol
TORY_LLM_TIMEOUT=20
OPENAI_API_KEY=segredo
```

Nunca versionar as credenciais. Em produção, usar o mecanismo de secrets do
ambiente de implantação.

## Segurança e permissões

- apenas HTTPS é aceito;
- redirecionamentos e links de detalhe devem permanecer na mesma origem;
- a integração só faz `POST` no login e `GET` nas consultas;
- credenciais, cookies e payloads não são gravados em logs;
- admin pode consultar todos os resultados autorizados à conta técnica;
- demais perfis só recebem resultados que tenham correspondência com um
  inventário local dentro das bases/regionais já autorizadas;
- resultados externos sem correspondência segura são omitidos;
- falhas do Portal ou do LLM produzem resposta segura, sem dados presumidos.

## Limitações conhecidas

O Portal não expõe neste projeto um contrato público de API para esses dados.
A integração lê os mesmos envelopes JSON e fragmentos HTML usados pela tela.
Mudanças de URL, nomes dos controles ou estrutura das tabelas podem exigir
ajuste no parser. Por isso, a flag deve ser habilitada primeiro para um piloto e
os testes de contrato devem ser atualizados com HTML real sanitizado quando o
layout do Portal mudar.

Não houve teste ponta a ponta no Portal de produção porque nenhuma credencial
foi armazenada no repositório. Os testes automatizados usam respostas simuladas.

## Rollback

Definir `TORY_LLM_ENABLED=False` desliga apenas o LLM e mantém as regras locais.
Definir `INVENTORY_PORTAL_ENABLED=False` desliga toda a leitura do Portal sem
migration, alteração de banco ou perda de dados.
