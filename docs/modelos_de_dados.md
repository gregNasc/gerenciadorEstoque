# 05 — Modelos de Dados

## Objetivo

Este documento descreve os principais modelos de dados do Gerenciador de Estoque.

A intenção não é apenas listar campos, mas explicar o papel de cada entidade dentro do domínio do sistema.

---

# 1. Visão Geral dos Domínios

O sistema é dividido em dois grandes domínios principais:

```text
Estoque
├── Empresas
├── Bases
├── Grupos de Bases
├── Usuários
├── Produtos
├── Equipamentos
├── Transferências
├── Empréstimos
├── SICK
└── Histórico

Insumos
├── Categorias
├── Insumos
├── Movimentações
├── Solicitações
├── Clientes
├── Inventários
├── Checklists
├── TAGs
├── Consumo
└── Histórico
```

---

# 2. Domínio Estoque

## 2.1 Empresa

### Objetivo

Representa a organização principal dona das bases e operações.

### Responsabilidades

* agrupar bases;
* vincular usuários por perfil;
* separar dados quando necessário;
* servir como unidade organizacional principal.

### Relacionamentos

```text
Empresa
   └── Bases
        └── Equipamentos
```

### Regras

* uma empresa pode possuir várias bases;
* usuários podem ser vinculados indiretamente à empresa por meio do perfil;
* a empresa deve ser respeitada nos filtros de acesso.

### Melhorias Futuras

* suporte multiempresa mais robusto;
* configurações específicas por empresa;
* identidade visual por empresa.

---

## 2.2 Grupo de Bases

### Objetivo

Representa o agrupamento de várias bases.

Esse conceito é importante para indicadores executivos, empréstimos e análise gerencial.

### Responsabilidades

* agrupar bases relacionadas;
* permitir visão consolidada;
* apoiar regras de movimentação entre bases;
* permitir análise de custo por grupo.

### Relacionamentos

```text
Grupo de Bases
   ├── Base A
   ├── Base B
   └── Base C
```

### Regras

* base e grupo não são a mesma coisa;
* dashboards executivos devem diferenciar custo por base e custo por grupo;
* “regional” não deve ser usado como sinônimo automático de grupo sem validação.

### Melhorias Futuras

* painel por grupo;
* permissões por grupo;
* metas de custo por grupo;
* comparação entre grupos.

---

## 2.3 Base

### Objetivo

Representa uma unidade operacional.

É o ponto central de estoque, equipamentos, insumos, usuários e inventários.

### Responsabilidades

* armazenar equipamentos;
* armazenar saldos de insumos;
* vincular usuários;
* vincular inventários;
* participar de transferências e empréstimos;
* alimentar dashboards operacionais.

### Relacionamentos

```text
Base
├── Equipamentos
├── Inventários
├── Movimentações de Insumos
├── Lotes de TAGs
└── Usuários via Perfil
```

### Regras

* todo equipamento deve estar vinculado a uma base;
* toda movimentação de insumo deve ocorrer em uma base;
* usuários de base só devem operar bases vinculadas ao seu perfil;
* inventários devem estar associados a uma base.

### Melhorias Futuras

* metas de estoque por base;
* ranking de consumo por base;
* alertas automáticos por base;
* dashboard operacional específico.

---

## 2.4 Perfil

### Objetivo

Complementa o usuário do Django com informações operacionais.

### Responsabilidades

* definir papel do usuário;
* vincular usuário à empresa;
* vincular usuário às bases permitidas;
* controlar permissões visuais e operacionais.

### Relacionamentos

```text
User
 └── Perfil
      ├── Empresa
      └── Bases
```

### Regras

* todo usuário deve possuir perfil;
* perfil define o nível de acesso;
* gestores podem ter múltiplas bases;
* operadores devem atuar apenas nas bases permitidas;
* administradores têm visão ampla.

### Melhorias Futuras

* suporte a perfis por grupo;
* idioma preferencial do usuário;
* preferências de dashboard;
* assinatura de notificações.

---

## 2.5 Produto

### Objetivo

Representa o tipo ou modelo do equipamento.

Exemplos:

* coletor;
* impressora;
* notebook;
* router.

### Responsabilidades

* classificar equipamentos;
* agrupar estoque por modelo;
* alimentar filtros;
* alimentar dashboards;
* permitir análise por categoria.

### Relacionamentos

```text
Produto
 └── Equipamentos
```

### Regras

* um produto pode possuir vários equipamentos;
* produto não representa item físico individual;
* o equipamento é a unidade física rastreável.

### Melhorias Futuras

* padronização de categorias;
* vida útil esperada;
* fabricante homologado;
* compatibilidade com clientes ou operações.

---

## 2.6 Equipamento

### Objetivo

Representa um ativo físico controlado pelo sistema.

### Responsabilidades

* identificar número de série;
* identificar patrimônio;
* controlar base atual;
* controlar status;
* participar de transferências;
* participar de empréstimos;
* participar de checklists;
* gerar histórico;
* alimentar dashboards.

### Relacionamentos

```text
Produto
   └── Equipamento
          ├── Base
          ├── Histórico
          ├── SICK
          ├── Transferências
          ├── Empréstimos
          └── ChecklistEquipamento
```

### Regras

* número de série deve ser único;
* patrimônio deve ser único quando informado;
* equipamento só pode pertencer a uma base por vez;
* equipamento em SICK, manutenção, baixa ou transferência não deve ser tratado como disponível;
* toda ação relevante deve gerar histórico.

### Melhorias Futuras

* QR Code;
* etiqueta patrimonial;
* vida útil;
* histórico de manutenção;
* custo por equipamento preparado, mas não usado inicialmente;
* rastreamento por inventário.

---

## 2.7 SICK

### Objetivo

Representa um equipamento com problema, defeito ou pendência operacional.

### Responsabilidades

* registrar motivo;
* registrar categoria do problema;
* retirar equipamento da disponibilidade;
* registrar resolução;
* alimentar indicadores de manutenção.

### Relacionamentos

```text
Equipamento
   └── SICK
```

### Regras

* equipamento marcado como SICK deve mudar de status;
* SICK deve gerar histórico;
* equipamento em SICK não deve aparecer como disponível;
* resolução deve registrar data e observação.

### Melhorias Futuras

* categorias mais detalhadas;
* anexos;
* reincidência por equipamento;
* tempo médio em SICK;
* dashboard de problemas por base;
* análise de falhas por modelo.

---

## 2.8 Histórico

### Objetivo

Registrar eventos importantes relacionados aos equipamentos.

### Responsabilidades

* manter auditoria;
* registrar usuário responsável;
* registrar tipo de ação;
* armazenar detalhes em JSON;
* permitir rastreabilidade.

### Relacionamentos

```text
Equipamento
   └── Histórico
```

### Regras

* toda ação relevante deve gerar histórico;
* histórico não deve ser apagado em fluxo normal;
* detalhes devem ser claros o suficiente para auditoria.

### Melhorias Futuras

* histórico global unificado;
* filtros avançados;
* exportação;
* timeline por equipamento;
* integração com notificações.

---

## 2.9 Solicitação

### Objetivo

Representa uma solicitação de equipamentos entre bases.

### Responsabilidades

* registrar produto solicitado;
* registrar quantidade;
* registrar base solicitante;
* registrar base origem;
* controlar aprovação;
* iniciar fluxo de transferência.

### Relacionamentos

```text
Solicitação
 ├── Produto
 ├── Base Solicitante
 ├── Base Origem
 ├── Usuário Solicitante
 └── Transferências
```

### Regras

* solicitação deve possuir status;
* solicitação aprovada pode gerar transferência;
* solicitação rejeitada deve registrar responsável;
* solicitação finalizada deve refletir equipamentos recebidos.

### Melhorias Futuras

* SLA de atendimento;
* prioridade;
* justificativa estruturada;
* painel de solicitações pendentes.

---

## 2.10 Transferência

### Objetivo

Representa o deslocamento definitivo ou operacional de equipamento entre bases.

### Responsabilidades

* controlar origem;
* controlar destino;
* controlar equipamento;
* controlar status;
* registrar envio;
* registrar recebimento;
* registrar divergência.

### Relacionamentos

```text
Solicitação
   └── Transferência
          └── Equipamento
```

### Regras

* equipamento em transferência não deve ser usado por outra operação;
* recebimento deve confirmar se chegou corretamente;
* divergência deve ser registrada;
* transferência deve gerar histórico.

### Melhorias Futuras

* comprovante de envio;
* anexos;
* rastreio;
* assinatura de recebimento;
* integração com notificações.

---

## 2.11 Empréstimo

### Objetivo

Representa empréstimo temporário de equipamento entre bases.

### Responsabilidades

* registrar base origem;
* registrar base destino;
* registrar equipamento;
* controlar recebimento;
* controlar devolução;
* confirmar finalização.

### Fluxo

```text
Aguardando recebimento
↓
Emprestado
↓
Aguardando confirmação de devolução
↓
Finalizado
```

### Regras

* empréstimo não é transferência definitiva;
* equipamento deve retornar à base de origem;
* devolução precisa de confirmação;
* histórico deve ser gerado.

### Melhorias Futuras

* prazo previsto de devolução;
* alertas de atraso;
* painel de empréstimos em aberto;
* bloqueio automático por pendência.

---

# 3. Domínio Insumos

## 3.1 CategoriaInsumo

### Objetivo

Classificar insumos por grupo operacional.

Exemplos:

* Departamento Pessoal;
* EPI;
* Operacional;
* Fios e Cabos;
* TAGs.

### Responsabilidades

* organizar cadastro;
* alimentar filtros;
* alimentar dashboards por categoria;
* apoiar análise de consumo.

### Relacionamentos

```text
CategoriaInsumo
   └── Insumos
```

### Regras

* nome da categoria deve ser único;
* categorias devem ser claras para evitar duplicidade;
* categorias devem apoiar a operação e os dashboards.

### Melhorias Futuras

* ícone por categoria;
* ordenação customizada;
* categoria financeira;
* agrupamento executivo.

---

## 3.2 Insumo

### Objetivo

Representa um material utilizado na operação.

Pode ser consumível, reutilizável ou controlado por lote.

### Responsabilidades

* identificar o material;
* definir unidade de medida;
* definir tipo de controle;
* armazenar valor médio;
* definir estoque mínimo;
* definir estoque máximo;
* controlar status ativo;
* alimentar movimentações, checklists e custos.

### Tipos de Controle

```text
QUANTIDADE
LOTE
REUTILIZAVEL
```

### Exemplos

Consumíveis:

* sulfite;
* máscara;
* luva;
* touca.

Reutilizáveis:

* durex;
* balança;
* escada;
* botas;
* transformadores.

Controle por lote:

* TAGs.

### Relacionamentos

```text
CategoriaInsumo
   └── Insumo
          ├── Movimentações
          ├── ItemChecklist
          ├── ConsumoInsumo
          └── Solicitações
```

### Regras

* insumo deve pertencer a uma categoria;
* insumo inativo não deve aparecer para novas movimentações;
* compras pode cadastrar novos insumos;
* compras pode atualizar preços;
* bases usam os itens cadastrados por compras;
* estoque mínimo deve alimentar alerta de compra.

### Melhorias Futuras

* fornecedor principal;
* prazo médio de entrega;
* estoque de segurança;
* curva ABC;
* classificação por criticidade;
* histórico de preço;
* unidade de compra diferente da unidade de consumo.

---

## 3.3 SolicitaçãoInsumo

### Objetivo

Representa pedido de reposição ou compra de insumos.

### Responsabilidades

* registrar base solicitante;
* registrar solicitante;
* controlar status;
* registrar aprovação;
* registrar finalização;
* agrupar itens solicitados.

### Relacionamentos

```text
SolicitaçãoInsumo
   ├── Base
   ├── Solicitante
   └── ItemSolicitacaoInsumo
```

### Regras

* solicitação deve possuir protocolo;
* solicitação deve ter status;
* compras pode acompanhar e finalizar;
* aprovação/reprovação deve registrar observação quando necessário.

### Melhorias Futuras

* workflow de aprovação;
* integração com compras;
* anexos de cotação;
* previsão de entrega;
* prioridade.

---

## 3.4 ItemSolicitacaoInsumo

### Objetivo

Representa cada item dentro de uma solicitação de insumo.

### Responsabilidades

* vincular insumo;
* registrar quantidade;
* compor solicitação;
* permitir análise do pedido.

### Relacionamentos

```text
SolicitaçãoInsumo
   └── ItemSolicitacaoInsumo
          └── Insumo
```

### Regras

* quantidade deve ser maior que zero;
* item deve pertencer a uma solicitação;
* item deve apontar para um insumo existente.

### Melhorias Futuras

* quantidade aprovada;
* quantidade comprada;
* valor estimado;
* fornecedor sugerido.

---

## 3.5 MovimentacaoInsumo

### Objetivo

Registrar toda entrada, saída, devolução, perda ou ajuste de insumo em uma base.

### Tipos

```text
ENTRADA
SAIDA
DEVOLUCAO
PERDA
AJUSTE_ENTRADA
AJUSTE_SAIDA
```

### Responsabilidades

* registrar base;
* registrar insumo;
* registrar tipo;
* registrar quantidade;
* registrar valor unitário;
* registrar usuário;
* registrar observação;
* alimentar saldo;
* alimentar histórico;
* alimentar dashboards.

### Relacionamentos

```text
Base
 └── MovimentacaoInsumo
        └── Insumo
```

### Regras

* entrada aumenta saldo;
* devolução aumenta saldo;
* ajuste de entrada aumenta saldo;
* saída reduz saldo;
* perda reduz saldo;
* ajuste de saída reduz saldo;
* saída não deve permitir saldo negativo;
* perda deve impactar custo;
* ajuste deve ter justificativa.

### Melhorias Futuras

* vínculo formal com documento de compra;
* lote de compra;
* nota fiscal;
* anexos;
* auditoria avançada.

---

## 3.6 Cliente

### Objetivo

Representa o cliente para o qual o inventário é realizado.

### Responsabilidades

* identificar cliente por sigla;
* agrupar inventários;
* permitir análise de custo por cliente;
* alimentar dashboards executivos.

### Relacionamentos

```text
Cliente
   └── Inventários
```

### Regras

* sigla deve ser única;
* cliente inativo não deve aparecer para novos inventários;
* cliente deve ser usado nos dashboards de custo.

### Melhorias Futuras

* contrato;
* meta de custo;
* SLA;
* segmento;
* custo médio esperado.

---

## 3.7 Inventario

### Objetivo

Representa uma operação de inventário realizada para cliente, loja e base.

### Responsabilidades

* registrar cliente;
* registrar loja;
* registrar base;
* registrar período;
* controlar status;
* vincular checklist;
* consolidar custo individual;
* alimentar dashboards.

### Relacionamentos

```text
Cliente
   └── Inventário
          ├── Base
          ├── ChecklistDiario
          └── ConsumoInsumo
```

### Regras

* inventário deve ter cliente;
* inventário deve ter loja;
* inventário deve ter base;
* inventário pode estar planejado, em andamento ou finalizado;
* custo individual deve ser calculado a partir do consumo efetivo.

### Melhorias Futuras

* integração com sistema de planejamento;
* previsão de consumo;
* quantidade de operadores;
* duração real;
* custo por hora;
* margem por cliente.

---

## 3.8 ChecklistDiario

### Objetivo

Representa o checklist operacional de um inventário.

É uma das entidades centrais do módulo de insumos.

### Responsabilidades

* controlar abertura;
* controlar finalização;
* vincular responsável;
* registrar observações;
* agrupar equipamentos;
* agrupar insumos;
* agrupar TAGs;
* gerar consumo;
* gerar movimentações;
* gerar histórico.

### Relacionamentos

```text
Inventário
   └── ChecklistDiario
          ├── ItemChecklist
          ├── ChecklistEquipamento
          └── ChecklistLoteTag
```

### Regras

* checklist deve estar vinculado a um inventário;
* checklist aberto ainda pode ser editado;
* checklist finalizado não deve permitir alterações operacionais comuns;
* finalização deve validar retorno de equipamentos;
* finalização deve validar conciliação de insumos;
* finalização deve gerar consumo e movimentações.

### Melhorias Futuras

* assinatura digital;
* anexos;
* checklist por etapas;
* status intermediários;
* aprovação de divergência;
* impressão em PDF.

---

## 3.9 ItemChecklist

### Objetivo

Representa um insumo enviado em um checklist.

### Responsabilidades

* registrar insumo;
* registrar quantidade enviada;
* registrar quantidade utilizada;
* registrar quantidade retornada;
* registrar quantidade perdida;
* permitir cálculo de consumo;
* permitir cálculo de custo.

### Relacionamentos

```text
ChecklistDiario
   └── ItemChecklist
          └── Insumo
```

### Regras

A regra de conciliação é:

```text
utilizada + retornada + perdida = enviada
```

Para consumíveis, quantidade utilizada gera custo.

Para reutilizáveis, apenas quantidade consumida, perdida ou descartada gera custo.

Itens retornados não devem gerar custo consumido.

### Melhorias Futuras

* estado parcial do item;
* motivo da perda;
* condição de retorno;
* foto do item;
* aprovação de divergência.

---

## 3.10 ChecklistEquipamento

### Objetivo

Representa equipamento enviado e retornado em um checklist.

### Responsabilidades

* vincular equipamento;
* registrar TAG de saída;
* registrar TAG de retorno;
* registrar data de retorno;
* registrar observação;
* garantir rastreabilidade.

### Relacionamentos

```text
ChecklistDiario
   └── ChecklistEquipamento
          └── Equipamento
```

### Regras

* equipamento deve estar disponível na base;
* equipamento enviado deve ter retorno registrado;
* checklist não deve finalizar com equipamento pendente;
* divergências devem ser observadas.

### Melhorias Futuras

* status de retorno;
* avaria no retorno;
* assinatura de responsável;
* leitura por QR Code;
* vínculo com ocorrência SICK.

---

## 3.11 ChecklistLoteTag

### Objetivo

Representa a faixa de TAG enviada e retornada em um checklist.

### Responsabilidades

* vincular checklist;
* vincular lote de TAG;
* registrar faixa enviada;
* registrar faixa retornada;
* permitir cálculo de TAG utilizada;
* permitir cálculo de custo.

### Relacionamentos

```text
ChecklistDiario
   └── ChecklistLoteTag
          └── LoteTag
```

### Regras

* faixa enviada deve pertencer ao lote;
* número final deve ser maior ou igual ao inicial;
* consumo da faixa é inclusivo;
* retorno deve permitir cálculo do consumo;
* custo deve ser calculado pelo valor unitário da TAG.

### Fórmula

```text
quantidade_enviada = final_enviado - inicial_enviado + 1
quantidade_retornada = final_retorno - inicial_retorno + 1
quantidade_utilizada = quantidade_enviada - quantidade_retornada
```

### Melhorias Futuras

* múltiplas faixas por checklist;
* bloqueio de sobreposição;
* reserva temporária de faixa;
* leitura por código;
* auditoria de lacunas.

---

## 3.12 LoteTag

### Objetivo

Representa um lote ou rolo de TAGs disponível em uma base.

### Responsabilidades

* controlar faixa inicial;
* controlar faixa final;
* controlar valor do rolo;
* controlar quantidade total;
* controlar quantidade disponível;
* permitir movimentações;
* permitir cálculo de custo unitário.

### Relacionamentos

```text
Base
   └── LoteTag
          ├── MovimentacaoTag
          └── ChecklistLoteTag
```

### Regras

* lote pertence a uma base;
* lote deve ter número inicial e final;
* quantidade total deve ser calculada pela faixa;
* quantidade disponível deve refletir consumo, retorno e perdas;
* valor unitário da TAG vem do valor do rolo dividido pela quantidade total.

### Exemplo

```text
Valor do rolo: R$ 18,00
Quantidade: 1000 TAGs
Custo unitário: R$ 0,018
```

### Melhorias Futuras

* reserva de faixa;
* alerta de lote acabando;
* controle de lotes inativos;
* histórico visual de consumo;
* regra para faixas especiais.

---

## 3.13 MovimentacaoTag

### Objetivo

Registrar movimentações específicas de TAGs por faixa.

### Tipos

```text
ENVIO
RETORNO
PERDA
```

### Responsabilidades

* registrar inventário;
* registrar lote;
* registrar faixa;
* registrar tipo;
* registrar usuário;
* alimentar histórico;
* permitir auditoria de TAGs.

### Relacionamentos

```text
Inventário
   └── MovimentacaoTag
          └── LoteTag
```

### Regras

* movimentação deve apontar para lote;
* faixa deve ser válida;
* perda deve gerar custo;
* envio e retorno devem permitir conciliação.

### Melhorias Futuras

* bloqueio de faixa duplicada;
* auditoria por número individual;
* mapa de faixas usadas;
* dashboard de consumo de TAG.

---

## 3.14 ConsumoInsumo

### Objetivo

Representa o custo efetivo de insumo consumido em um inventário.

### Responsabilidades

* vincular inventário;
* vincular item de checklist;
* vincular insumo;
* registrar quantidade consumida;
* registrar valor unitário;
* registrar valor total;
* alimentar dashboards financeiros e executivos.

### Relacionamentos

```text
Inventário
   └── ConsumoInsumo
          ├── ItemChecklist
          └── Insumo
```

### Regras

* só deve existir consumo quando houver quantidade efetivamente consumida ou perdida;
* item retornado não deve gerar consumo;
* valor total deve ser calculado por quantidade × valor unitário;
* custo do inventário é a soma dos consumos.

### Dashboards Impactados

* custo por inventário;
* custo por cliente;
* custo por base;
* custo por grupo;
* custo por mês;
* consumo por categoria;
* perdas;
* desperdício;
* reutilização.

### Melhorias Futuras

* separação entre consumo e perda;
* custo previsto versus custo real;
* classificação financeira;
* curva de consumo por cliente.

---

## 3.15 HistoricoInsumo

### Objetivo

Registrar eventos importantes do domínio de insumos.

### Responsabilidades

* registrar movimentações;
* registrar consumo;
* registrar checklist;
* registrar usuário;
* armazenar dados adicionais em JSON;
* permitir auditoria.

### Relacionamentos

```text
HistoricoInsumo
 ├── Usuário
 └── Dados JSON
```

### Regras

* eventos relevantes devem gerar histórico;
* histórico deve ser claro;
* histórico não deve ser apagado em fluxo comum;
* dados JSON devem ajudar auditoria e suporte.

### Melhorias Futuras

* histórico unificado com estoque;
* timeline por inventário;
* exportação;
* filtros por tipo;
* integração com notificações.

---

# 4. Relacionamentos Principais

## 4.1 Estrutura Organizacional

```text
Empresa
   └── Grupo de Bases
          └── Base
                 ├── Usuários
                 ├── Equipamentos
                 ├── Insumos
                 └── Inventários
```

---

## 4.2 Estoque de Equipamentos

```text
Produto
   └── Equipamento
          ├── Base
          ├── SICK
          ├── Histórico
          ├── Transferência
          └── Empréstimo
```

---

## 4.3 Inventário e Checklist

```text
Cliente
   └── Inventário
          └── Checklist
                 ├── Equipamentos
                 ├── Insumos
                 └── TAGs
```

---

## 4.4 Consumo e Custo

```text
Checklist
   └── ItemChecklist
          └── ConsumoInsumo
                 └── Dashboards
```

---

## 4.5 TAGs

```text
Base
   └── LoteTag
          ├── ChecklistLoteTag
          └── MovimentacaoTag
```

---

# 5. Regras Transversais

## 5.1 Auditoria

Toda movimentação importante deve gerar histórico.

Exemplos:

* transferência;
* empréstimo;
* SICK;
* movimentação de insumo;
* finalização de checklist;
* consumo;
* perda;
* ajuste.

---

## 5.2 Disponibilidade

Um item só deve ser apresentado como disponível se estiver em condição operacional.

Para equipamentos:

* não pode estar em SICK;
* não pode estar em manutenção;
* não pode estar em transferência;
* não pode estar baixado;
* não pode estar indisponível por empréstimo.

Para insumos:

* deve estar ativo;
* deve ter saldo suficiente;
* deve pertencer à base correta.

---

## 5.3 Custo

O custo deve ser calculado com base no consumo efetivo.

```text
Enviado não significa consumido.
Retornado não gera custo consumido.
Perdido gera custo.
Utilizado gera custo.
```

---

## 5.4 Reutilização

Insumos reutilizáveis devem permitir retorno ao estoque.

Exemplo:

```text
Enviado: 5
Retornado: 4
Consumido/perdido: 1
Custo: 1 unidade
```

---

## 5.5 Estoque Mínimo

Insumos devem permitir configuração de estoque mínimo.

Quando o saldo estiver abaixo do mínimo, o sistema deve sinalizar necessidade de compra.

---

# 6. Modelos Planejados ou Evoluções Futuras

## 6.1 Fornecedor

Modelo futuro para controlar fornecedores de insumos.

Possíveis campos:

* nome;
* CNPJ;
* contato;
* telefone;
* e-mail;
* prazo médio de entrega;
* ativo.

---

## 6.2 HistoricoPrecoInsumo

Modelo futuro para armazenar alterações de preço.

Possíveis campos:

* insumo;
* valor anterior;
* valor novo;
* usuário;
* data;
* observação.

---

## 6.3 ConfiguracaoReposicao

Modelo futuro para regras de compra.

Possíveis campos:

* insumo;
* base;
* estoque mínimo;
* estoque máximo;
* ponto de reposição;
* lead time;
* estoque de segurança.

---

## 6.4 EventoNotificacao

Modelo futuro para sistema de notificações plugável.

Possíveis campos:

* tipo;
* origem;
* mensagem;
* canal;
* status;
* usuário destino;
* criado em;
* enviado em.

---

## 6.5 IntegracaoPlanejamento

Modelo futuro para registrar dados importados ou sincronizados via API externa.

Possíveis campos:

* sistema origem;
* identificador externo;
* payload;
* status;
* data de sincronização;
* erro.

---

# 7. Tempos operacionais do Inventario

O modelo `Inventario` preserva `data_inicio`, `data_fim` e os horários legados para compatibilidade com calendários e importações existentes. A medição operacional usa os campos aditivos:

```text
inicio_previsto
fim_previsto
inicio_real
fim_real
inicio_contagem
fim_contagem
pessoas
total_pecas
custo_hora_pessoa
```

Os timestamps são opcionais para permitir migração gradual do histórico. Durações, desvios, produtividade e custo adicional são valores derivados e não devem ser persistidos como uma jornada fixa.

---

# 8. Conclusão

Os modelos de dados do Gerenciador de Estoque representam mais do que tabelas.

Eles representam a operação da empresa.

A Fase 2 deve preservar essa lógica:

```text
Operação real
↓
Regra de negócio
↓
Modelo de dados
↓
Service
↓
Interface
↓
Dashboard
```

O objetivo é manter o domínio claro, rastreável e preparado para crescimento.
