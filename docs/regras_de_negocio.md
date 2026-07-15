# 03 — Regras de Negócio

## Objetivo

Este documento registra as principais regras de negócio do Gerenciador de Estoque.

Ele deve ser usado como referência oficial para implementação, refatoração, testes, dashboards e futuras integrações.

---

## 1. Princípio Geral

O sistema deve representar a operação real.

Nenhuma regra crítica deve existir apenas no template ou apenas na cabeça do usuário.
Toda regra importante deve estar documentada e implementada preferencialmente em services.

---

# 2. Estrutura Operacional

## 2.1 Empresa

A empresa representa o nível mais alto de organização do sistema.

Uma empresa pode possuir várias bases.

---

## 2.2 Base

A base representa uma unidade operacional.

Uma base pode possuir:

* equipamentos;
* insumos;
* usuários;
* inventários;
* checklists;
* movimentações;
* solicitações;
* histórico.

Os usuários de base operam principalmente dentro das bases vinculadas ao seu perfil.

---

## 2.3 Grupo de Bases

Um grupo é um agrupamento de bases.

Indicadores executivos devem diferenciar:

* custo por base;
* custo por grupo.

Base e grupo não são a mesma coisa.

---

## 2.4 Cliente

Cliente representa a empresa ou operação para a qual o inventário é realizado.

O cliente pode ser identificado por sigla.

Exemplos:

* OXX;
* PDA;
* EXS.

O cliente é importante para análise de custo, consumo e rentabilidade operacional.

---

# 3. Usuários e Perfis

## 3.1 Administrador

Pode acessar e gerenciar todas as áreas do sistema.

Responsabilidades:

* usuários;
* permissões;
* cadastros;
* configurações;
* visão geral;
* manutenção do sistema.

---

## 3.2 Gestor

Pode acompanhar e operar dados das bases vinculadas ao seu perfil.

Responsabilidades:

* acompanhar estoque;
* solicitar transferências;
* receber equipamentos;
* acompanhar SICK;
* visualizar dashboards permitidos.

---

## 3.3 Operador

Usuário operacional.

Responsabilidades:

* cadastrar equipamentos quando permitido;
* registrar movimentações autorizadas;
* abrir ou preencher checklists;
* marcar SICK;
* registrar retornos;
* consultar dados operacionais.

---

## 3.4 Compras

Usuário responsável pela gestão de insumos sob o ponto de vista de aquisição.

Responsabilidades:

* cadastrar novos insumos;
* atualizar preços;
* definir estoque mínimo;
* definir estoque máximo ou ponto de reposição;
* visualizar necessidade de compra;
* acompanhar consumo histórico;
* acompanhar projeção de compras.

Compras não deve depender de planilhas externas para saber o que precisa ser comprado.

---

## 3.5 Planejamento

Usuário responsável pela visão futura da operação.

Responsabilidades:

* acompanhar inventários;
* prever demanda;
* consultar necessidade futura de insumos;
* acompanhar capacidade operacional;
* consumir ou fornecer dados via API externa futuramente.

---

## 3.6 Financeiro

Usuário responsável por análise financeira.

Responsabilidades:

* visualizar custos;
* analisar consumo;
* acompanhar perdas;
* acompanhar desperdício;
* acompanhar custo por inventário;
* acompanhar custo por cliente, base e grupo.

---

## 3.7 Executivo

Usuário responsável por tomada de decisão estratégica.

Responsabilidades:

* visualizar indicadores consolidados;
* acompanhar custos;
* acompanhar consumo;
* acompanhar perdas;
* acompanhar reutilização;
* acompanhar tendência mensal;
* acompanhar projeções.

---

# 4. Estoque de Equipamentos

## 4.1 Equipamento

Um equipamento representa um bem físico controlado pelo sistema.

Pode possuir:

* produto;
* número de série;
* patrimônio;
* base atual;
* responsável;
* status;
* foto;
* histórico.

---

## 4.2 Status do Equipamento

Os status devem representar a situação operacional do equipamento.

Exemplos:

* ativo;
* transferência;
* manutenção;
* SICK;
* baixa;
* emprestado.

Um equipamento não deve estar disponível para uso se estiver em status incompatível com operação.

---

## 4.3 Histórico de Equipamento

Toda ação relevante em um equipamento deve gerar histórico.

Exemplos:

* criação;
* edição;
* alteração de status;
* transferência;
* recebimento;
* cancelamento;
* envio para SICK;
* resolução de SICK;
* empréstimo;
* devolução.

O histórico deve permitir auditoria.

---

# 5. Transferências

## 5.1 Solicitação de Transferência

Uma transferência pode nascer de uma solicitação entre bases.

A solicitação deve registrar:

* produto;
* quantidade;
* base solicitante;
* base origem;
* usuário solicitante;
* usuário aprovador;
* status;
* datas relevantes.

---

## 5.2 Aprovação

A transferência deve seguir fluxo controlado.

Exemplo:

```text
Pendente
↓
Aprovada
↓
Em transferência
↓
Recebida
↓
Finalizada
```

---

## 5.3 Recebimento

O recebimento deve confirmar se o equipamento chegou corretamente.

Pode haver divergência.

Exemplos:

* recebido corretamente;
* recebido com divergência;
* não recebido.

---

# 6. Empréstimos

## 6.1 Empréstimos entre Bases

Empréstimos ocorrem entre bases, normalmente respeitando agrupamentos definidos.

Fluxo esperado:

```text
Aguardando recebimento
↓
Emprestado
↓
Aguardando confirmação de devolução
↓
Finalizado
```

---

## 6.2 Devolução

A devolução deve ser confirmada pela base de origem.

Apenas após confirmação o empréstimo deve ser considerado finalizado.

---

# 7. SICK

## 7.1 Conceito

SICK representa equipamentos com problema, defeito, pendência ou necessidade de análise/manutenção.

---

## 7.2 Marcação de SICK

Ao marcar um equipamento como SICK:

* o status do equipamento deve mudar;
* deve ser criado registro SICK;
* deve ser criado histórico;
* o equipamento deve sair da disponibilidade operacional.

---

## 7.3 Resolução de SICK

Ao resolver um SICK:

* deve ser registrada a solução;
* o histórico deve ser atualizado;
* o equipamento pode voltar para ativo ou outro status definido;
* a data de resolução deve ser salva.

---

## 7.4 Melhorias Futuras

O módulo SICK deverá ser refatorado para melhorar:

* categorização;
* filtros;
* histórico;
* anexos;
* análise por tipo de problema;
* indicadores por base;
* reincidência por equipamento.

---

# 8. Insumos

## 8.1 Conceito

Insumos são materiais utilizados na operação.

Podem ser consumíveis, reutilizáveis ou controlados por lote.

---

## 8.2 Tipos de Controle

### Quantidade

Controle simples por quantidade.

Exemplos:

* sulfite;
* máscara;
* luva;
* touca.

---

### Lote

Controle por faixa, lote ou numeração.

Exemplo:

* TAGs.

---

### Reutilizável

Material que pode ser enviado para um inventário e retornar para uso futuro.

Exemplos:

* durex;
* balança;
* escada;
* botas;
* transformadores.

O custo só deve ser apropriado quando houver consumo efetivo, perda ou descarte.

---

## 8.3 Cadastro de Insumos

Compras deve poder cadastrar novos insumos.

Ao cadastrar um insumo, deve ser possível definir:

* descrição;
* categoria;
* unidade de medida;
* tipo de controle;
* valor unitário ou valor médio;
* estoque mínimo;
* estoque máximo;
* status ativo/inativo.

Após o cadastro, o item deve ficar disponível para as bases movimentarem em seus estoques.

---

## 8.4 Preço dos Insumos

Compras deve poder atualizar preços.

O sistema deve preservar a possibilidade de custo médio, especialmente quando houver entradas com preços diferentes.

---

## 8.5 Estoque Mínimo

Cada insumo pode possuir estoque mínimo.

Quando o saldo estiver abaixo do mínimo, o sistema deve sinalizar necessidade de compra.

Essa informação deve aparecer para Compras e, quando necessário, nos dashboards gerenciais.

---

## 8.6 Estoque Máximo ou Ponto de Reposição

O sistema deve permitir preparar regra futura para estoque máximo ou ponto de reposição.

Isso ajudará Compras a evitar tanto falta quanto excesso.

---

# 9. Movimentações de Insumos

## 9.1 Entrada

Entrada aumenta o saldo do insumo em uma base.

Pode ocorrer por:

* compra;
* cadastro inicial;
* ajuste;
* devolução operacional.

---

## 9.2 Saída

Saída reduz o saldo.

Pode ocorrer por:

* envio para inventário;
* consumo;
* ajuste;
* descarte;
* perda.

---

## 9.3 Devolução

Devolução retorna item ao estoque.

Deve ser usada quando o item enviado não foi consumido.

---

## 9.4 Perda

Perda registra item enviado que não retornou ou foi danificado.

Perda deve impactar custo.

---

## 9.5 Ajuste

Ajuste corrige divergência entre saldo físico e saldo do sistema.

O ajuste deve registrar:

* saldo anterior;
* saldo real;
* diferença;
* usuário;
* justificativa.

---

# 10. Inventários

## 10.1 Conceito

Inventário representa uma operação realizada para determinado cliente, loja e base.

Deve registrar:

* cliente;
* loja;
* base;
* data de início;
* data de fim;
* status;
* responsável;
* usuário criador.

---

## 10.2 Status do Inventário

Exemplos:

```text
Planejado
↓
Em andamento
↓
Finalizado
```

---

## 10.3 Custo Individual

Cada inventário deve possuir custo individual calculado.

Esse custo deve considerar:

* insumos consumidos;
* TAGs utilizadas;
* perdas;
* itens reutilizáveis efetivamente consumidos ou perdidos.

Itens enviados e retornados não devem compor o custo consumido.

---

# 11. Checklist

## 11.1 Conceito

Checklist é o registro operacional do que foi enviado e retornado em um inventário.

Deve controlar:

* equipamentos;
* insumos;
* TAGs;
* retornos;
* perdas;
* consumo;
* observações.

---

## 11.2 Abertura do Checklist

Ao abrir um checklist:

* deve estar vinculado a um inventário;
* deve possuir responsável;
* deve possuir status;
* deve registrar data de início.

---

## 11.3 Envio de Equipamentos

O checklist deve permitir selecionar equipamentos disponíveis na base.

Exemplos:

* coletores;
* impressoras;
* notebooks;
* routers.

Equipamentos indisponíveis não devem ser enviados.

---

## 11.4 Retorno de Equipamentos

Para finalizar o checklist, os equipamentos enviados devem ter retorno registrado.

O sistema deve controlar:

* equipamento;
* tag de saída;
* tag de retorno;
* data de retorno;
* observação.

---

## 11.5 Envio de Insumos

O checklist deve permitir informar insumos enviados.

O sistema deve validar saldo disponível.

Não deve permitir envio maior que o saldo da base.

---

## 11.6 Retorno de Insumos

Na finalização, deve ser informado o que foi:

* utilizado;
* retornado;
* perdido.

A regra básica é:

```text
quantidade_utilizada + quantidade_retornada + quantidade_perdida = quantidade_enviada
```

---

## 11.7 Reutilização

Para insumos reutilizáveis, o sistema deve permitir retorno sem gerar custo consumido.

Exemplo:

```text
Enviado: 3 durex
Retornado: 2 durex
Utilizado/perdido: 1 durex
Custo calculado: 1 unidade
```

Se tudo retornar, o custo consumido deve ser zero.

---

# 12. TAGs

## 12.1 Conceito

TAGs são insumos com controle especial por faixa numérica.

São compradas em rolos, normalmente com 1000 unidades.

---

## 12.2 Lote de TAG

Um lote deve possuir:

* base;
* número inicial;
* número final;
* valor do rolo;
* quantidade total;
* quantidade disponível;
* status ativo.

---

## 12.3 Custo Unitário da TAG

O custo unitário deve ser calculado assim:

```text
valor_do_rolo / quantidade_total_do_lote
```

Exemplo:

```text
R$ 18,00 / 1000 = R$ 0,018
```

---

## 12.4 Consumo por Faixa

O consumo da faixa deve ser inclusivo.

Exemplo:

```text
Inicial: 5000
Final: 5345
```

Quantidade utilizada:

```text
5345 - 5000 + 1 = 346
```

Custo:

```text
346 × 0,018 = R$ 6,23
```

---

## 12.5 Envio e Retorno de TAG

O checklist deve registrar:

* lote;
* número inicial enviado;
* número final enviado;
* número inicial retornado;
* número final retornado.

O consumo deve ser calculado pela diferença entre faixa enviada e faixa retornada.

---

## 12.6 Perda de TAG

Se houver perda de TAG, o sistema deve registrar movimentação e custo correspondente.

---

# 13. Consumo

## 13.1 Conceito

Consumo é o que efetivamente virou custo para o inventário.

Não é necessariamente igual ao que foi enviado.

---

## 13.2 Regra Principal

```text
Custo do inventário = soma dos insumos efetivamente consumidos ou perdidos
```

---

## 13.3 Itens Retornados

Itens retornados ao estoque não devem compor custo consumido.

---

## 13.4 Itens Reutilizáveis

Itens reutilizáveis só devem gerar custo quando:

* forem utilizados até acabar;
* forem perdidos;
* forem descartados;
* forem danificados sem retorno.

---

# 14. Custos

## 14.1 Custo por Inventário

Cada inventário deve ter custo total calculado.

Esse custo deve ser consultável por:

* inventário;
* cliente;
* loja;
* base;
* grupo;
* período.

---

## 14.2 Custo por Cliente

Permite identificar quanto cada cliente consome em insumos.

---

## 14.3 Custo por Base

Permite identificar consumo e custo de cada base.

---

## 14.4 Custo por Grupo

Permite análise consolidada dos grupos de bases.

---

## 14.5 Custo por Mês

Permite acompanhar evolução mensal.

---

## 14.6 Custo Médio por Inventário

Regra:

```text
custo_total_no_periodo / quantidade_de_inventarios_no_periodo
```

---

## 14.7 Consumo por Categoria

Permite identificar quais categorias mais consomem recursos.

---

# 15. Perdas e Desperdício

## 15.1 Perda

Perda é item enviado que não retornou ou foi danificado.

Perda deve gerar custo.

---

## 15.2 Desperdício

Desperdício é consumo acima do esperado ou uso desnecessário.

O sistema deve preparar indicadores para comparar:

* consumo médio por inventário;
* consumo por cliente;
* consumo por base;
* consumo por grupo;
* consumo por categoria;
* perdas por período.

---

## 15.3 Reutilização como Redução de Desperdício

O sistema deve medir quanto foi reutilizado.

Exemplo:

```text
Valor enviado: R$ 500,00
Valor consumido: R$ 120,00
Valor retornado/reutilizado: R$ 380,00
```

---

# 16. Compras

## 16.1 Papel de Compras

Compras deve ter visão sobre:

* estoque baixo;
* consumo histórico;
* preços;
* novos itens;
* projeção de compra;
* itens mais consumidos;
* perdas;
* custo por categoria.

---

## 16.2 Alerta de Estoque Baixo

O sistema deve sinalizar quando:

```text
saldo_atual <= estoque_minimo
```

---

## 16.3 Projeção de Compras

A projeção deve considerar futuramente:

* consumo médio;
* inventários planejados;
* sazonalidade;
* estoque atual;
* estoque mínimo;
* prazo de reposição.

---

# 17. Planejamento

## 17.1 Papel do Planejamento

Planejamento deve acompanhar:

* inventários previstos;
* inventários em andamento;
* necessidade de equipamentos;
* necessidade de insumos;
* demanda futura.

---

## 17.2 Integração Externa

Existe outro sistema de Planejamento.

O Gerenciador de Estoque deve ser preparado para integração via API.

O documento técnico da integração será analisado futuramente.

---

# 18. Dashboards

## 18.1 Dashboard Principal

Deve melhorar a visualização e análise do estoque.

Deve responder:

* quantos equipamentos existem;
* onde estão;
* qual status;
* quais bases possuem maior ou menor estoque;
* quais produtos estão críticos;
* quais equipamentos estão em SICK;
* quais movimentações estão pendentes.

---

## 18.2 Dashboard Compras

Deve responder:

* o que precisa comprar;
* qual item está abaixo do mínimo;
* qual item mais consome;
* qual categoria mais custa;
* qual a projeção para o próximo mês;
* quais preços foram atualizados.

---

## 18.3 Dashboard Planejamento

Deve responder:

* quais inventários estão previstos;
* quais estão em andamento;
* quais recursos serão necessários;
* qual consumo previsto;
* quais bases podem precisar de reposição.

---

## 18.4 Dashboard Executivo

Deve responder:

* custo por cliente;
* custo por base;
* custo por grupo;
* custo por mês;
* custo médio por inventário;
* consumo por categoria;
* perdas;
* desperdício;
* reutilização;
* projeção de compras.

---

# 19. Comunicados e Notificações

## 19.1 Conceito

Comunicados registram eventos importantes do sistema.

Notificações devem evoluir para múltiplos canais.

---

## 19.2 Canais

Canais previstos:

* dashboard interno;
* e-mail;
* WhatsApp;
* push futuramente.

---

## 19.3 Regra Principal

A ação operacional não deve depender diretamente do canal.

Fluxo desejado:

```text
Ação operacional
↓
Evento registrado
↓
Comunicado criado
↓
Notificação enviada pelos canais configurados
```

---

# 20. Internacionalização

## 20.1 Idiomas

O sistema deve ser preparado para:

* português;
* espanhol.

---

## 20.2 Regra

Textos fixos devem ser evitados.

Templates, forms, models e mensagens devem usar recursos de tradução sempre que possível.

---

# 21. Infraestrutura

## 21.1 Ambiente Atual

O sistema roda atualmente no Render.

---

## 21.2 Migração Futura

Deve ser planejada uma futura migração de infraestrutura.

Essa migração deve considerar:

* banco de dados;
* arquivos estáticos;
* arquivos de mídia;
* variáveis de ambiente;
* domínio;
* backup;
* deploy;
* monitoramento.

---

# 22. Regra de Evolução da Fase 2

Toda melhoria importante deve seguir:

```text
Ideia
↓
Discussão
↓
Documentação
↓
Validação
↓
Implementação
↓
Teste
↓
Deploy
```

---

# 23. Tempos operacionais dos inventários e Tory

## 23.1 Intervalos completos

Inventários não possuem uma jornada fixa. Eles podem ser diurnos, noturnos, começar ou terminar em horários variados e atravessar a meia-noite.

A Tory deve usar exclusivamente datas e horários completos registrados em:

* `inicio_previsto` e `fim_previsto`;
* `inicio_real` e `fim_real`;
* `inicio_contagem` e `fim_contagem`.

O intervalo 20h–6h é apenas um exemplo operacional e nunca deve ser usado como padrão implícito.

## 23.2 Indicadores derivados

Com dados completos, o sistema deve calcular:

* duração prevista e duração real total;
* atraso ou antecipação de início e término;
* tempo efetivo de contagem;
* tempo fora da contagem;
* peças por pessoa;
* produtividade por pessoa/hora pela duração total;
* produtividade por pessoa/hora durante a contagem;
* custo adicional pelo tempo após o fim previsto, quando houver custo por pessoa/hora.

Registros incompletos continuam válidos, mas a Tory deve informar que o indicador não é calculável. Ela não deve preencher horários ausentes com uma jornada presumida.

## 23.3 Simulações

Simulações de horário e tamanho de equipe devem declarar a hipótese utilizada. A projeção linear mantém a produtividade individual observada e não representa garantia, pois pode haver perda de eficiência com equipes maiores.

## 23.4 Equipe produtiva e alocações

Para ciclos compostos por várias etapas, a soma de pessoas de `CA`, `CP`, `PRE`, `T`, `APOIO` e outras etapas representa **alocações pessoa-etapa**, não pessoas únicas trabalhando simultaneamente.

Nos cálculos de produtividade e duração da contagem oficial, a equipe produtiva deve ser:

```text
equipe_contagem = pessoas_T + pessoas_APOIO
duracao_planejada = previsao_pecas / equipe_contagem / produtividade_planejada
```

`prod_media` importada do planejamento deve ser apresentada como produtividade planejada em peças por pessoa/hora. Produtividade real só pode ser calculada com peças realizadas, quantidade real de pessoas e timestamps reais.

## 23.5 Contexto e desambiguação de bases

Quando um nome puder representar simultaneamente uma base e uma UF, como “São Paulo”, a Tory deve pedir confirmação e oferecer as bases acessíveis como opções clicáveis. “UF SP” e “estado de São Paulo” selecionam explicitamente a UF.

Ao selecionar uma base, a Tory deve apenas completar o filtro pendente. A intenção original, a data, o período, o cliente e a loja devem ser preservados. Identificadores de loja podem ser numéricos ou alfanuméricos, como `A063`.

---

## Conclusão

As regras de negócio devem guiar o desenvolvimento.

O objetivo do sistema não é apenas controlar estoque, mas gerar inteligência operacional e financeira para a tomada de decisão.

Este documento deve ser revisado sempre que uma regra importante mudar.
