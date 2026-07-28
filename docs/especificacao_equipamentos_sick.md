# ESPECIFICAÇÃO PARA O CODEX
## Classificação de equipamentos, contexto de base e novo fluxo de SICK/manutenção

Projeto: `gerenciadorEstoque`  
Framework: Django 5.2.6  
Aplicativo principal afetado: `estoque`

---

# 1. OBJETIVO

Implementar três melhorias relacionadas ao controle de equipamentos:

1. Permitir classificar cada equipamento como:
   - `OPERACIONAL`
   - `ADMINISTRATIVO`

2. Melhorar a experiência de seleção de base:
   - quando o usuário já tiver selecionado uma base no filtro ou contexto da tela, essa base deve ser automaticamente utilizada nas ações realizadas sobre equipamentos;
   - não deve ser necessário selecionar novamente a mesma base dentro de modais ou formulários.

3. Transformar o processo de SICK em um fluxo rastreável até a manutenção e o retorno do equipamento.

Todas as ações relacionadas ao fluxo de SICK devem:

- gerar registro no histórico do equipamento;
- gerar comunicado para todos os usuários administradores;
- respeitar as permissões e regionais do usuário que executa a ação;
- ser executadas dentro de transação atômica quando alterarem mais de um registro.

---

# 2. REGRA DE CLASSIFICAÇÃO DO EQUIPAMENTO

## 2.1. Nova finalidade

Adicionar ao model `Equipamento` um campo que represente a finalidade do equipamento.

Exemplo:

```python
class Equipamento(models.Model):

    FINALIDADES = [
        ("OPERACIONAL", "Operacional"),
        ("ADMINISTRATIVO", "Administrativo"),
    ]

    finalidade = models.CharField(
        max_length=20,
        choices=FINALIDADES,
        default="OPERACIONAL",
        db_index=True,
    )
```

## 2.2. Regra de migração

Todos os equipamentos existentes devem receber:

```text
finalidade = OPERACIONAL
```

A migration não deve alterar o status atual de nenhum equipamento.

## 2.3. Separação entre finalidade e status

A finalidade não substitui o status.

Exemplos válidos:

```text
OPERACIONAL + ATIVO
ADMINISTRATIVO + ATIVO
OPERACIONAL + SICK
ADMINISTRATIVO + SICK
OPERACIONAL + MANUTENCAO
ADMINISTRATIVO + MANUTENCAO
```

Não criar `ADMINISTRATIVO` como um novo status.

A finalidade representa o uso do equipamento.

O status representa a situação atual do equipamento.

---

# 3. REGRAS DE CONTAGEM

## 3.1. Total de equipamentos

Todo equipamento deve permanecer visível na contagem total, inclusive equipamentos administrativos.

```python
total_equipamentos = equipamentos.count()
```

## 3.2. Ativos operacionais

O card, KPI ou contador denominado `Ativos` deve contar exclusivamente:

```python
equipamentos.filter(
    status="ATIVO",
    finalidade="OPERACIONAL",
)
```

Equipamentos administrativos não podem ser contabilizados como ativos operacionais.

## 3.3. Administrativos

Criar uma contagem própria para equipamentos administrativos.

Exemplo:

```python
administrativos = equipamentos.filter(
    finalidade="ADMINISTRATIVO",
).exclude(status="BAIXA")
```

## 3.4. Outras contagens

Equipamentos administrativos continuam aparecendo normalmente em:

- total de equipamentos;
- SICK;
- manutenção;
- transferência;
- baixa;
- histórico;
- resultados de pesquisa;
- modais de detalhamento.

---

# 4. EXIBIÇÃO DO EQUIPAMENTO

## 4.1. Badges

A interface deve mostrar separadamente:

- finalidade;
- status.

Exemplos:

```text
[Operacional] [Ativo]
[Administrativo] [SICK]
[Administrativo] [Em manutenção]
```

Quando um equipamento estiver com:

```text
status = ATIVO
finalidade = ADMINISTRATIVO
```

a interface não deve induzir o usuário a acreditar que ele faz parte dos ativos operacionais.

Exibir preferencialmente:

```text
[Administrativo]
```

ou:

```text
[Administrativo] [Disponível internamente]
```

Não incluir esse equipamento no total de ativos operacionais.

## 4.2. Formulários

Adicionar o campo `finalidade` nos formulários de:

- cadastro de equipamento;
- edição de equipamento;
- eventual edição rápida em modal.

Valor padrão:

```text
OPERACIONAL
```

## 4.3. Permissões sugeridas

- Admin pode alterar a finalidade de qualquer equipamento.
- Gestor pode alterar a finalidade de equipamentos pertencentes às suas regionais.
- Operador pode visualizar a finalidade.
- Caso a regra atual do projeto permita que operadores editem equipamentos, manter as permissões existentes, mas validar regional e empresa.

## 4.4. Histórico da mudança

Toda alteração de finalidade deve gerar histórico.

Exemplo de detalhes:

```python
{
    "campo": "finalidade",
    "valor_anterior": "OPERACIONAL",
    "valor_novo": "ADMINISTRATIVO",
}
```

---

# 5. MELHORIAS NOS MODAIS DO ESTOQUE

Os modais de detalhamento devem mostrar de forma clara:

- empresa;
- base;
- categoria;
- produto;
- fabricante;
- modelo;
- número de série;
- patrimônio;
- finalidade;
- status;
- responsável;
- situação atual de SICK;
- datas importantes do SICK, quando existirem.

## 5.1. Resumo do modal

Exibir contadores como:

```text
Total
Ativos operacionais
Administrativos
SICK
Em manutenção
Em transferência
Baixa
```

## 5.2. Filtros internos

Adicionar, quando aplicável:

- Todos;
- Operacionais;
- Administrativos;
- Ativos operacionais;
- SICK;
- Em trânsito para manutenção;
- Recebidos pela manutenção;
- Em avaliação;
- Em manutenção;
- Aguardando retorno;
- Baixa.

## 5.3. Visualização para admin

Quando o admin visualizar resultados de várias empresas ou bases, cada equipamento deve mostrar claramente:

```text
Empresa
Base
Finalidade
Status
```

Evitar que equipamentos de bases diferentes pareçam pertencer ao mesmo agrupamento.

---

# 6. CONTEXTO AUTOMÁTICO DA BASE

## 6.1. Regra principal

Quando uma base já tiver sido selecionada no filtro ou contexto da tela, essa base deve ser reutilizada automaticamente nas ações subsequentes.

Exemplo:

```text
Empresa selecionada: OXXO
Base selecionada: OXXO SP INT BAURU X
```

Ao abrir um modal de cadastro, edição, SICK ou movimentação, não solicitar novamente a escolha dessa base.

## 6.2. Front-end

A base pode ser enviada por:

- campo hidden;
- atributo `data-base-id`;
- query string;
- variável de contexto da página.

Exemplo:

```html
<input
    type="hidden"
    name="regional"
    value="{{ base_selecionada.id }}"
>
```

Exibir o nome da base em campo somente leitura.

## 6.3. Backend

Nunca confiar somente no campo hidden.

Sempre validar:

- se a base existe;
- se pertence à empresa esperada;
- se o usuário tem acesso à base;
- se o equipamento pertence à base informada;
- se o admin está operando dentro do contexto selecionado.

## 6.4. Usuário com uma única base

Quando o perfil tiver apenas uma regional, utilizar essa base automaticamente.

## 6.5. Usuário com várias bases

Quando o usuário tiver várias regionais:

- usar a base selecionada no filtro;
- manter a seleção ao abrir os modais;
- exigir escolha somente quando nenhuma base estiver definida.

---

# 7. NOVO FLUXO DE SICK

# 7.1. Conceito

O status principal do equipamento e a etapa do SICK devem ser separados.

O equipamento continuará utilizando os status principais existentes, principalmente:

```text
ATIVO
SICK
MANUTENCAO
TRANSFERENCIA
BAIXA
```

O model `Sick` deve informar em qual etapa do processo o equipamento se encontra.

---

# 8. ETAPAS DO SICK

Adicionar ao model `Sick` um campo `etapa`.

Exemplo:

```python
ETAPAS = [
    ("IDENTIFICADO", "Identificado na base"),
    ("EM_TRANSITO", "Em trânsito para manutenção"),
    ("RECEBIDO", "Recebido pela manutenção"),
    ("EM_AVALIACAO", "Em avaliação técnica"),
    ("EM_MANUTENCAO", "Em manutenção"),
    ("AGUARDANDO_RETORNO", "Aguardando retorno para a base"),
    ("FINALIZADO", "Finalizado"),
]
```

Campo:

```python
etapa = models.CharField(
    max_length=30,
    choices=ETAPAS,
    default="IDENTIFICADO",
    db_index=True,
)
```

---

# 9. CAMPOS SUGERIDOS PARA O MODEL SICK

Adaptar ao model atual sem apagar informações já existentes.

Campos sugeridos:

```python
motivo_inicial = models.TextField()

enviado_manutencao_em = models.DateTimeField(
    null=True,
    blank=True,
)

enviado_manutencao_por = models.ForeignKey(
    User,
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
    related_name="sicks_enviados_manutencao",
)

recebido_manutencao_em = models.DateTimeField(
    null=True,
    blank=True,
)

recebido_manutencao_por = models.ForeignKey(
    User,
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
    related_name="sicks_recebidos_manutencao",
)

avaliacao_iniciada_em = models.DateTimeField(
    null=True,
    blank=True,
)

avaliacao_iniciada_por = models.ForeignKey(
    User,
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
    related_name="sicks_avaliados",
)

manutencao_iniciada_em = models.DateTimeField(
    null=True,
    blank=True,
)

manutencao_iniciada_por = models.ForeignKey(
    User,
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
    related_name="sicks_manutencao_iniciada",
)

manutencao_concluida_em = models.DateTimeField(
    null=True,
    blank=True,
)

manutencao_concluida_por = models.ForeignKey(
    User,
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
    related_name="sicks_manutencao_concluida",
)

retorno_confirmado_em = models.DateTimeField(
    null=True,
    blank=True,
)

retorno_confirmado_por = models.ForeignKey(
    User,
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
    related_name="sicks_retorno_confirmado",
)

destino_manutencao = models.CharField(
    max_length=255,
    blank=True,
)

protocolo_envio = models.CharField(
    max_length=100,
    blank=True,
)

transportadora_ou_portador = models.CharField(
    max_length=255,
    blank=True,
)

causa_identificada = models.TextField(
    blank=True,
)

diagnostico = models.TextField(
    blank=True,
)

solucao_aplicada = models.TextField(
    blank=True,
)

observacao_tecnica = models.TextField(
    blank=True,
)
```

Caso já exista uma estrutura equivalente, reaproveitar os campos atuais e evitar duplicidade.

---

# 10. TRANSIÇÕES DO FLUXO

## 10.1. Marcar equipamento como SICK

Ação:

```text
Marcar como SICK
```

Resultado:

```text
Equipamento.status = SICK
Sick.etapa = IDENTIFICADO
```

Informações mínimas:

- categoria do problema;
- motivo;
- observação;
- usuário;
- data;
- base atual.

O equipamento deve ficar indisponível para uso operacional.

Gerar:

- histórico;
- comunicado para todos os admins.

---

## 10.2. Enviar para manutenção

Ação:

```text
Enviar para manutenção
```

Permitida somente quando:

```text
Sick.etapa = IDENTIFICADO
```

Informações:

- data e hora do envio;
- destino da manutenção;
- responsável pelo envio;
- transportadora ou portador, opcional;
- protocolo ou rastreio, opcional;
- observação, opcional.

Resultado:

```text
Equipamento.status = SICK
Sick.etapa = EM_TRANSITO
```

Exibição:

```text
SICK / Em trânsito
Equipamento enviado para manutenção em DD/MM/AAAA.
```

Gerar:

- histórico;
- comunicado para todos os admins.

---

## 10.3. Confirmar recebimento pela manutenção

Ação:

```text
Confirmar recebimento
```

Permitida somente quando:

```text
Sick.etapa = EM_TRANSITO
```

Resultado:

```text
Equipamento.status = SICK
Sick.etapa = RECEBIDO
```

O equipamento ainda não deve mudar para `MANUTENCAO`.

Gerar:

- histórico;
- comunicado para todos os admins.

---

## 10.4. Iniciar avaliação técnica

Ação:

```text
Iniciar avaliação
```

Permitida somente quando:

```text
Sick.etapa = RECEBIDO
```

Resultado:

```text
Equipamento.status = SICK
Sick.etapa = EM_AVALIACAO
```

Gerar:

- histórico;
- comunicado para todos os admins.

---

## 10.5. Iniciar manutenção

Ação:

```text
Iniciar manutenção
```

Permitida somente quando:

```text
Sick.etapa = EM_AVALIACAO
```

Exigir:

- causa identificada;
- diagnóstico;
- observação técnica ou ação planejada.

Resultado:

```text
Equipamento.status = MANUTENCAO
Sick.etapa = EM_MANUTENCAO
```

Gerar:

- histórico;
- comunicado para todos os admins.

---

## 10.6. Concluir manutenção

Ação:

```text
Concluir manutenção
```

Permitida somente quando:

```text
Sick.etapa = EM_MANUTENCAO
```

Exigir:

- solução aplicada;
- resultado;
- indicação se o equipamento possui condição de retornar;
- observações.

Quando reparado:

```text
Equipamento.status = SICK
Sick.etapa = AGUARDANDO_RETORNO
```

O equipamento não deve voltar automaticamente para `ATIVO`.

Gerar:

- histórico;
- comunicado para todos os admins.

Caso não tenha reparo, manter fluxo separado para baixa ou decisão administrativa.

Não realizar baixa automática.

---

## 10.7. Confirmar retorno para a base

Ação:

```text
Confirmar retorno
```

Permitida somente quando:

```text
Sick.etapa = AGUARDANDO_RETORNO
```

Resultado:

```text
Equipamento.status = ATIVO
Sick.etapa = FINALIZADO
```

A finalidade deve ser preservada.

Exemplos:

```text
OPERACIONAL volta a ser ativo operacional.
ADMINISTRATIVO volta a estar disponível administrativamente,
mas não entra na contagem de ativos operacionais.
```

Gerar:

- histórico;
- comunicado para todos os admins.

---

# 11. COMUNICADOS OBRIGATÓRIOS PARA ADMIN

## 11.1. Regra geral

Toda ação referente ao SICK deve gerar comunicado para todos os usuários cujo perfil possua:

```text
role = admin
```

ou que pertençam ao grupo administrativo equivalente utilizado no projeto.

Não gerar comunicado apenas para o usuário que executou a ação.

O comunicado deve ser enviado para todos os admins ativos.

## 11.2. Ações que obrigatoriamente geram comunicado

- equipamento marcado como SICK;
- informações do SICK editadas;
- equipamento enviado para manutenção;
- envio para manutenção cancelado, se essa ação existir;
- equipamento recebido pela manutenção;
- avaliação técnica iniciada;
- diagnóstico atualizado;
- manutenção iniciada;
- manutenção atualizada;
- manutenção concluída;
- equipamento definido como sem reparo;
- equipamento aguardando retorno;
- retorno confirmado pela base;
- SICK finalizado;
- SICK reaberto;
- qualquer mudança manual de etapa;
- qualquer cancelamento ou reversão de etapa.

## 11.3. Conteúdo mínimo do comunicado

Cada comunicado deve conter:

- título;
- equipamento;
- número de série;
- patrimônio;
- produto/modelo;
- empresa;
- base;
- etapa anterior;
- nova etapa;
- usuário responsável;
- data e hora;
- observação relevante;
- link para abrir os detalhes do equipamento ou do SICK.

Exemplo de título:

```text
Equipamento enviado para manutenção
```

Exemplo de mensagem:

```text
O equipamento Notebook Dell Latitude 5420,
série ABC123 e patrimônio PAT-00987,
da base OXXO SP INT BAURU X,
foi enviado para manutenção em 16/07/2026 às 15:20
por João Silva.

Situação atual: SICK / Em trânsito.
Destino: Manutenção Central.
```

## 11.4. Serviço centralizado

Não duplicar a criação de comunicados em várias views.

Criar ou reaproveitar um serviço centralizado, por exemplo:

```python
class ComunicadoSickService:

    @staticmethod
    def notificar_admins(
        *,
        sick,
        acao,
        usuario,
        etapa_anterior=None,
        etapa_nova=None,
        detalhes=None,
    ):
        ...
```

Esse serviço deve:

1. localizar todos os admins ativos;
2. criar um comunicado para cada admin ou criar um comunicado global conforme a arquitetura atual;
3. evitar duplicidade;
4. armazenar dados estruturados em JSON, quando o model permitir;
5. incluir URL para os detalhes;
6. ser chamado somente após a alteração ser validada.

## 11.5. Transação

Histórico, alteração do SICK, alteração do equipamento e geração dos comunicados devem ocorrer dentro da mesma transação quando possível.

Exemplo:

```python
@transaction.atomic
def enviar_para_manutencao(...):
    ...
```

Se houver falha na criação do histórico ou comunicado, a operação não deve ficar parcialmente concluída.

Caso a arquitetura atual use `transaction.on_commit`, garantir que:

- a alteração principal seja concluída;
- o comunicado não seja duplicado;
- falhas externas não corrompam o fluxo.

---

# 12. HISTÓRICO

Adicionar ou reutilizar tipos de histórico equivalentes a:

```python
("SICK", "Marcado como SICK"),
("SICK_ATUALIZADO", "SICK atualizado"),
("SICK_ENVIO_MANUTENCAO", "Enviado para manutenção"),
("SICK_RECEBIMENTO_MANUTENCAO", "Recebido pela manutenção"),
("SICK_AVALIACAO", "Avaliação técnica iniciada"),
("MANUTENCAO_INICIADA", "Manutenção iniciada"),
("MANUTENCAO_ATUALIZADA", "Manutenção atualizada"),
("MANUTENCAO_CONCLUIDA", "Manutenção concluída"),
("SICK_AGUARDANDO_RETORNO", "Aguardando retorno"),
("SICK_RETORNO_CONFIRMADO", "Retorno confirmado"),
("RESOLUCAO_SICK", "SICK finalizado"),
("SICK_REABERTO", "SICK reaberto"),
]
```

Os detalhes devem conter dados estruturados.

Exemplo:

```python
{
    "sick_id": sick.id,
    "etapa_anterior": "IDENTIFICADO",
    "etapa_nova": "EM_TRANSITO",
    "origem": equipamento.regional.nome,
    "destino": sick.destino_manutencao,
    "data_acao": timezone.now().isoformat(),
    "usuario_id": usuario.id,
    "usuario_nome": usuario.get_full_name() or usuario.username,
}
```

---

# 13. SERVIÇO DE DOMÍNIO

Evitar concentrar as regras diretamente nas views.

Criar um serviço, por exemplo:

```text
estoque/services/sick_service.py
```

Classe sugerida:

```python
class SickService:

    @staticmethod
    @transaction.atomic
    def marcar_como_sick(...):
        ...

    @staticmethod
    @transaction.atomic
    def enviar_para_manutencao(...):
        ...

    @staticmethod
    @transaction.atomic
    def confirmar_recebimento(...):
        ...

    @staticmethod
    @transaction.atomic
    def iniciar_avaliacao(...):
        ...

    @staticmethod
    @transaction.atomic
    def iniciar_manutencao(...):
        ...

    @staticmethod
    @transaction.atomic
    def concluir_manutencao(...):
        ...

    @staticmethod
    @transaction.atomic
    def confirmar_retorno(...):
        ...
```

Cada método deve:

1. validar permissão;
2. bloquear transições inválidas;
3. validar a etapa atual;
4. atualizar o `Equipamento`;
5. atualizar o `Sick`;
6. criar o `Historico`;
7. gerar comunicados para todos os admins;
8. retornar o resultado atualizado.

---

# 14. BLOQUEIO DE TRANSIÇÕES INVÁLIDAS

Não permitir pular etapas diretamente.

Fluxo padrão:

```text
IDENTIFICADO
    ↓
EM_TRANSITO
    ↓
RECEBIDO
    ↓
EM_AVALIACAO
    ↓
EM_MANUTENCAO
    ↓
AGUARDANDO_RETORNO
    ↓
FINALIZADO
```

Exemplos proibidos:

- iniciar manutenção antes de confirmar recebimento;
- concluir manutenção sem diagnóstico;
- retornar equipamento antes da conclusão;
- marcar como ativo enquanto estiver em trânsito;
- finalizar SICK sem confirmação de retorno;
- alterar diretamente a etapa por POST sem validação do serviço.

Admin pode ter ações de correção ou reversão, mas elas devem:

- exigir justificativa;
- gerar histórico;
- gerar comunicado para todos os admins;
- registrar etapa anterior e nova etapa.

---

# 15. PERMISSÕES

Criar ou reutilizar permissões equivalentes a:

```python
permissions = [
    ("enviar_equipamento_manutencao", "Pode enviar equipamento para manutenção"),
    ("receber_equipamento_manutencao", "Pode confirmar recebimento na manutenção"),
    ("avaliar_equipamento_sick", "Pode avaliar equipamento SICK"),
    ("iniciar_manutencao_equipamento", "Pode iniciar manutenção"),
    ("concluir_manutencao_equipamento", "Pode concluir manutenção"),
    ("confirmar_retorno_equipamento", "Pode confirmar retorno do equipamento"),
    ("corrigir_fluxo_sick", "Pode corrigir etapas do fluxo SICK"),
]
```

Sugestão de regras:

- Base:
  - marcar como SICK;
  - enviar para manutenção;
  - confirmar retorno.

- Equipe de manutenção:
  - confirmar recebimento;
  - iniciar avaliação;
  - iniciar manutenção;
  - concluir manutenção.

- Admin:
  - todas as ações;
  - correções mediante justificativa.

---

# 16. INTERFACE DO SICK

A tela deve mostrar uma timeline.

Exemplo:

```text
✓ Identificado na base
✓ Enviado para manutenção
✓ Recebido pela manutenção
● Em avaliação técnica
○ Em manutenção
○ Aguardando retorno
○ Finalizado
```

Exibir também:

- data e hora de cada etapa;
- usuário responsável;
- observações;
- destino;
- protocolo;
- diagnóstico;
- solução aplicada;
- histórico de alterações.

Os botões disponíveis devem depender da etapa atual e da permissão do usuário.

---

# 17. COMPATIBILIDADE COM DADOS EXISTENTES

Durante a migration:

- equipamentos existentes recebem `finalidade = OPERACIONAL`;
- registros SICK abertos existentes recebem `etapa = IDENTIFICADO`, salvo se os dados atuais permitirem inferir outra etapa com segurança;
- SICKs resolvidos existentes recebem `etapa = FINALIZADO`;
- não apagar campos ou históricos antigos;
- preservar compatibilidade com templates e views atuais até a conclusão da refatoração.

Criar migrations de dados quando necessário.

---

# 18. TESTES OBRIGATÓRIOS

Criar testes para:

## Finalidade

- novo equipamento recebe `OPERACIONAL` por padrão;
- equipamento pode ser alterado para `ADMINISTRATIVO`;
- administrativo permanece na contagem total;
- administrativo não entra na contagem de ativos operacionais;
- administrativo aparece em SICK e manutenção;
- alteração de finalidade gera histórico.

## Contexto da base

- base selecionada é reutilizada no modal;
- usuário com uma base recebe a base automaticamente;
- usuário não pode enviar base fora de suas regionais;
- admin consegue operar na base selecionada;
- equipamento não pode ser vinculado a base divergente sem validação.

## SICK

- marcar como SICK cria registro, histórico e comunicado;
- envio altera etapa para `EM_TRANSITO`;
- recebimento altera etapa para `RECEBIDO`;
- avaliação altera etapa para `EM_AVALIACAO`;
- manutenção altera status do equipamento para `MANUTENCAO`;
- conclusão altera etapa para `AGUARDANDO_RETORNO`;
- retorno altera etapa para `FINALIZADO`;
- retorno restaura `ATIVO`;
- finalidade administrativa é preservada;
- não é possível pular etapas;
- transições inválidas retornam erro;
- todas as ações geram comunicados para todos os admins;
- usuário não admin não recebe comunicado administrativo, salvo regra adicional existente;
- admin inativo não recebe comunicado;
- operação falha integralmente quando histórico ou alteração principal falhar.

---

# 19. CRITÉRIOS DE ACEITE

A implementação estará concluída quando:

1. Todo equipamento possuir finalidade operacional ou administrativa.
2. Equipamentos existentes permanecerem operacionais após a migration.
3. Equipamentos administrativos aparecerem no total, mas não em ativos operacionais.
4. Modais exibirem claramente base, finalidade e status.
5. A base selecionada na tela for reutilizada nas ações dos modais.
6. O usuário não precisar selecionar novamente a mesma base.
7. O fluxo de SICK possuir etapas rastreáveis.
8. Equipamento enviado permanecer como `SICK / Em trânsito`.
9. Equipamento recebido permanecer como `SICK`.
10. O status mudar para `MANUTENCAO` somente após avaliação e diagnóstico.
11. Equipamento concluído permanecer aguardando retorno.
12. Equipamento voltar para `ATIVO` somente após confirmação da base.
13. A finalidade original ser preservada durante todo o fluxo.
14. Toda ação de SICK gerar histórico.
15. Toda ação de SICK gerar comunicado para todos os admins ativos.
16. Transições inválidas serem bloqueadas.
17. Permissões e regionais serem respeitadas.
18. Haver testes cobrindo regras e transições.

---

# 20. ORDEM SUGERIDA DE IMPLEMENTAÇÃO

1. Mapear models, views, forms, templates, services e sistema atual de comunicados.
2. Criar campo `finalidade` e migration.
3. Ajustar formulários, filtros, cards, consultas e modais.
4. Implementar contexto automático da base.
5. Expandir o model `Sick`.
6. Criar migration de dados dos SICKs existentes.
7. Criar `SickService`.
8. Criar `ComunicadoSickService` ou adaptar o serviço atual.
9. Implementar as transições.
10. Ajustar permissões.
11. Criar timeline e botões condicionais.
12. Ajustar histórico.
13. Criar testes.
14. Executar:

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py check
python manage.py test
```

15. Revisar possíveis consultas antigas que considerem todo equipamento `ATIVO` como ativo operacional.

---

# 21. OBSERVAÇÃO IMPORTANTE AO CODEX

Antes de alterar os arquivos:

- inspecionar a implementação atual dos models `Equipamento`, `Sick`, `Historico` e `Comunicado`;
- localizar as views e services atuais de SICK;
- localizar como os admins são identificados;
- localizar como comunicados são criados;
- reaproveitar a arquitetura existente;
- evitar duplicar services, models ou regras;
- apresentar ao final a lista de arquivos alterados;
- informar migrations criadas;
- informar testes adicionados;
- informar qualquer incompatibilidade encontrada.

Não remover funcionalidades atuais sem substituir integralmente o comportamento.
