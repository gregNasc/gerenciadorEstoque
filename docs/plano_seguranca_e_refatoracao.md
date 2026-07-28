# Plano Primário de Segurança, Estabilização e Qualidade
## Projeto: gerenciadorEstoque

Este documento deve ser usado pelo Codex como guia da próxima janela de manutenção.

> **Objetivo principal:** melhorar segurança, eficiência e qualidade sem alterar o comportamento funcional atual do sistema.

O sistema está funcionando bem em produção e, por isso, as mudanças devem ser conservadoras, graduais e totalmente reversíveis.

---

# 0. REGRA OBRIGATÓRIA ANTES DE QUALQUER ALTERAÇÃO

## Criar snapshot completo do estado atual

Antes de editar qualquer arquivo:

1. Confirmar que o branch atual está atualizado.
2. Registrar o commit atual.
3. Criar uma branch exclusiva para a manutenção.
4. Criar uma tag ou branch de snapshot.
5. Gerar backup do banco de dados.
6. Registrar as variáveis e configurações necessárias para restaurar o ambiente.
7. Não trabalhar diretamente no branch `main`.

Fluxo sugerido:

```bash
git checkout main
git pull origin main

git status
git rev-parse HEAD

git branch snapshot/pre-hardening-2026
git push origin snapshot/pre-hardening-2026

git checkout -b refactor/security-hardening
git push -u origin refactor/security-hardening
```

Opcionalmente, criar também uma tag:

```bash
git tag snapshot-pre-hardening-2026
git push origin snapshot-pre-hardening-2026
```

## Backup do banco

Antes de migrations ou alterações estruturais:

```bash
pg_dump DATABASE_URL > backup_pre_hardening.sql
```

No Windows/PostgreSQL local, adaptar o comando conforme as credenciais e o ambiente.

## Critério de segurança

Nenhuma alteração deve prosseguir sem que exista:

- commit identificado;
- branch de snapshot;
- backup do banco;
- possibilidade clara de rollback.

---

# 1. PRINCÍPIOS DE EXECUÇÃO

O Codex deve seguir estas regras:

1. Não fazer refatoração ampla de uma só vez.
2. Não alterar regra de negócio sem evidência de erro.
3. Não remover model, campo, view ou template apenas por parecer antigo.
4. Antes de remover qualquer elemento, localizar todas as referências.
5. Criar testes de regressão antes de alterar fluxos sensíveis.
6. Trabalhar em commits pequenos e temáticos.
7. Rodar verificações após cada etapa.
8. Preservar o comportamento atual sempre que ele estiver funcionando.
9. Abrir Pull Request em modo draft.
10. Não fazer merge automático.

---

# 2. CORREÇÕES IMPORTANTES SOBRE AS REGRAS DE NEGÓCIO

## 2.1 `valor_medio` global no Insumo está correto

Não alterar a modelagem atual para custo médio por Base.

No domínio deste projeto, o valor do insumo é fixo/global e deve continuar armazenado no próprio `Insumo`.

Portanto:

```python
Insumo.valor_medio
```

deve permanecer como referência global.

Não criar `valor_medio` por Base nesta etapa.

Otimizações de saldo por Base podem ser consideradas futuramente, mas sem duplicar ou alterar a regra de valor global.

---

## 2.2 Diferença zero pode ser válida

Não tratar automaticamente `diferenca == 0` como erro.

Isso pode ocorrer de forma legítima, principalmente em fluxos de TAGs e em situações nas quais determinados itens existentes no estoque não são enviados para um inventário.

O Codex deve distinguir:

- item que não participou da operação;
- ajuste de estoque sem diferença;
- movimentação real de quantidade zero;
- registro de controle necessário para conciliação.

Antes de impedir movimentações de quantidade zero, verificar o contexto completo.

Regra recomendada:

```text
Quantidade zero não deve gerar efeito financeiro ou alterar saldo,
mas pode ser válida como resultado de conciliação ou ausência de envio.
```

Não remover essa possibilidade sem testes específicos para TAGs, checklist e finalização de inventários.

---

# 3. FASE 1 — SEGURANÇA DE CONFIGURAÇÃO

## 3.1 Corrigir `DEBUG`

Problema atual:

```python
DEBUG = True
```

Ajustar para variável de ambiente:

```python
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
```

Garantir:

- `False` em produção;
- `True` apenas no ambiente local;
- teste de inicialização nos dois ambientes.

## 3.2 Remover senha do banco do código

Remover credenciais fixas do `settings.py`.

Usar variáveis:

```text
DB_NAME
DB_USER
DB_PASSWORD
DB_HOST
DB_PORT
DATABASE_URL
```

Se a senha versionada ainda estiver em uso, deve ser trocada.

## 3.3 Tornar `SECRET_KEY` obrigatória em produção

Evitar fallback conhecido como:

```python
SECRET_KEY = os.getenv("SECRET_KEY", "unsafe-key")
```

Sugestão:

```python
SECRET_KEY = os.environ["SECRET_KEY"]
```

Se for necessário facilitar o ambiente local, separar configurações de desenvolvimento e produção.

## 3.4 Remover informações sensíveis dos logs

Remover:

```python
print(BASE_DIR)
print("DATABASE_URL =", DATABASE_URL)
```

Não registrar:

- senha;
- URL completa do banco;
- tokens;
- secrets;
- credenciais SMTP.

## 3.5 Configuração de e-mail

Substituir valores fictícios no código por variáveis de ambiente:

```text
EMAIL_HOST
EMAIL_PORT
EMAIL_USE_TLS
EMAIL_HOST_USER
EMAIL_HOST_PASSWORD
DEFAULT_FROM_EMAIL
```

Garantir que recuperação de senha continue funcionando.

## 3.6 Segurança HTTP em produção

Avaliar e configurar por ambiente:

```python
SECURE_SSL_REDIRECT
SECURE_HSTS_SECONDS
SECURE_HSTS_INCLUDE_SUBDOMAINS
SECURE_HSTS_PRELOAD
SESSION_COOKIE_SECURE
SESSION_COOKIE_HTTPONLY
SESSION_COOKIE_SAMESITE
CSRF_COOKIE_SECURE
CSRF_COOKIE_SAMESITE
SECURE_CONTENT_TYPE_NOSNIFF
X_FRAME_OPTIONS
```

Não aplicar configurações que quebrem o ambiente local.

## 3.7 WhiteNoise

Avaliar uso de:

```python
whitenoise.storage.CompressedManifestStaticFilesStorage
```

Antes de ativar, rodar:

```bash
python manage.py collectstatic --noinput
```

Verificar se não existem referências quebradas a arquivos estáticos.

---

# 4. FASE 2 — AUTENTICAÇÃO E PERMISSÕES

## 4.1 Proteger endpoints sem autenticação

Revisar todas as views e APIs.

Endpoints que acessam:

- equipamentos;
- patrimônios;
- números de série;
- lotes;
- TAGs;
- checklists;
- saldos;
- inventários;

devem possuir autenticação explícita.

Adicionar `@login_required` quando necessário.

## 4.2 Restringir APIs financeiras

Endpoints como:

- consumo por Base;
- consumo por mês;
- ranking de insumos;
- custos;
- perdas;
- valores de inventários;

devem exigir permissão financeira adequada.

Não confiar apenas na ocultação do menu.

A autorização deve estar no backend.

Exemplo:

```python
@permission_required(
    "insumos.visualizar_custos",
    raise_exception=True,
)
```

Também aplicar filtros por escopo quando necessário.

## 4.3 Centralizar escopo de acesso

Criar ou consolidar services como:

```python
BaseAccessService
EquipamentoAccessService
InventarioAccessService
InsumoAccessService
```

Objetivo:

```python
queryset = InventarioAccessService.for_user(request.user)
```

Evitar duplicação de regras em diversas views.

Essa camada também será importante para a futura Tory.

## 4.4 Revisar `role_required`

Ajustar o decorator para usar:

```python
from functools import wraps
```

Aplicar `@wraps(view_func)`.

Para usuários anônimos, preferir o comportamento padrão do Django com redirecionamento ao login.

## 4.5 Revisar ou remover `regional_required`

O decorator aparenta utilizar:

```python
perfil.regional
perfil.is_admin()
```

Mas o model atual trabalha com:

```python
perfil.regionais
perfil.is_admin
```

Localizar todas as referências.

Se não houver uso, remover em uma etapa separada.

Se houver uso, corrigir e adicionar testes.

---

# 5. FASE 3 — CORREÇÕES DE CONSISTÊNCIA

## 5.1 Estados de `Emprestimo`

Revisar a incompatibilidade entre choices e default.

Não alterar diretamente sem verificar dados existentes.

Criar script ou migration de dados caso existam registros com status antigos.

Definir um fluxo único.

## 5.2 Estados de `ItemEmprestimo`

Revisar o default `PENDENTE` versus choices atuais.

Verificar dados no banco antes de corrigir.

## 5.3 Estados de `Transferencia`

Atualmente há indícios de mistura entre:

```text
PENDENTE
EM_TRANSITO
CONCLUIDA
CANCELADA
```

e:

```text
ENVIADO
RECEBIDO
```

Mapear:

- views;
- services;
- templates;
- JavaScript;
- migrations;
- registros do banco;
- histórico.

Somente depois consolidar o fluxo.

## 5.4 Corrigir `Equipamento.__str__`

Como `produto` aceita `null`, tornar o método seguro:

```python
descricao = self.produto.descricao if self.produto else "Produto não informado"
```

Adicionar teste para equipamento sem produto.

## 5.5 Corrigir geração de código de equipamento

A lógica baseada no último `id` pode sofrer condição de corrida.

Não alterar sem teste de cadastro simultâneo.

Avaliar:

- UUID;
- sequence;
- geração após primeiro save;
- retry em caso de `IntegrityError`.

## 5.6 Constraints de banco

Adicionar gradualmente, após verificar dados existentes:

- quantidades não negativas;
- quantidades atendidas dentro do limite;
- datas coerentes;
- faixas de TAG válidas;
- estoque mínimo não negativo;
- estoque máximo maior ou igual ao mínimo.

Cada constraint deve ser adicionada em migration própria.

---

# 6. FASE 4 — DESEMPENHO

## 6.1 Eliminar consultas N × M do estoque de insumos

A tela atual percorre Bases e insumos e chama `saldo()` para cada combinação.

Criar consulta agregada única por:

```text
base_id
insumo_id
```

Usar `Sum` com filtros por tipo.

Não alterar a regra do `valor_medio`, que continuará global no `Insumo`.

## 6.2 Avaliar tabela de saldo por Base

Pode ser criada futuramente uma estrutura de saldo por Base para desempenho e concorrência.

Exemplo:

```python
class EstoqueInsumoBase(models.Model):
    base = ...
    insumo = ...
    saldo = ...
```

Importante:

```text
O valor do insumo permanece global.
A tabela por Base armazenaria somente saldo e dados operacionais.
```

Não implementar nesta primeira rodada sem plano de migração, testes e comparação de resultados.

## 6.3 Concorrência em movimentações

Apenas `transaction.atomic` não impede duas saídas simultâneas.

Avaliar uma estratégia com:

```python
select_for_update()
```

Isso pode exigir um registro de saldo por Base.

Enquanto a modelagem não for alterada, criar testes de concorrência e documentar o risco.

## 6.4 Otimizar consultas de grupos

Evitar várias consultas `.exists()` para os mesmos grupos do usuário.

Avaliar:

- `prefetch_related`;
- `cached_property`;
- cache dos nomes dos grupos durante a requisição.

## 6.5 Paginação e consultas relacionadas

Revisar listas grandes e garantir:

```python
select_related()
prefetch_related()
Paginator
```

Aplicar somente onde houver benefício comprovado.

---

# 7. FASE 5 — REFATORAÇÃO DE VIEWS

## 7.1 Dividir `insumos/views/api.py`

Sugestão:

```text
insumos/views/
    estoque.py
    inventarios.py
    checklists.py
    importacao.py
    api_estoque.py
    api_inventarios.py
    api_financeiro.py
```

Fazer essa divisão sem alterar URLs inicialmente.

Primeiro mover funções mantendo os mesmos nomes e comportamentos.

## 7.2 Separar parser/importador Excel

Mover funções de:

- normalização;
- descoberta de cabeçalho;
- resolução de Base;
- interpretação de planilhas;
- importação;

para:

```text
insumos/importers/
```

ou:

```text
insumos/services/importacao/
```

Criar testes unitários com arquivos de exemplo.

## 7.3 Reduzir imports duplicados

Executar ferramenta de lint, preferencialmente:

```bash
ruff check .
```

Não aplicar correções automáticas em massa sem revisão.

## 7.4 Nomear URLs

Adicionar `name=` aos endpoints que ainda não possuem nome.

Atualizar JavaScript e templates para usar URLs resolvidas pelo Django sempre que possível.

---

# 8. FASE 6 — CÓDIGO LEGADO E DESCARTE

Nenhum item deve ser excluído apenas por parecer obsoleto.

Criar uma matriz de uso para cada candidato:

```text
Elemento
Importado em
Chamado por URL
Usado em template
Usado no admin
Referenciado em migration
Possui registros no banco
Substituído por
Decisão
```

## Candidatos para investigação

### Models

- `PedidoTransferencia`
- `PedidoItem`
- `TransferRequest`
- `DivergenciaTransferencia`
- `Descricao`
- `Alerta`
- `Mensagem`
- `MensagemDestino`

Avaliar se foram substituídos por:

- `Transferencia`
- `PendenciaTransferencia`
- `Notificacao`
- `Comunicado`

### Views

- `finalizar_checklist_legado`
- `checklist_list`
- arquivos em `views_old`
- funções duplicadas
- endpoints não registrados em URLs
- funções sem chamadas

### Campos

- `data_criacao` versus `created_at`
- `criado_em` versus `created_at`
- campos comentados
- campos de versões antigas dos fluxos

### Dependências

Revisar uso real de:

- antiorm
- db
- db-sqlite3
- optional-django
- npm
- streamlit
- altair
- pydeck
- watchdog
- django-tailwind
- django-notifications-hq
- django-select2
- django-extensions
- django-model-utils
- jsonfield
- GitPython
- matplotlib
- pyarrow
- pandas-stubs
- pydantic
- reportlab
- anthropic

Não remover pacote sem buscar imports, comandos e arquivos que dependam dele.

---

# 9. TESTES OBRIGATÓRIOS

Antes de mudanças sensíveis, criar testes para:

## Segurança

- usuário anônimo não acessa APIs privadas;
- operador não acessa custos;
- financeiro acessa custos;
- usuário de uma empresa não acessa dados de outra;
- acesso direto por URL respeita permissões.

## Estoque

- entrada;
- saída;
- devolução;
- perda;
- ajuste;
- saldo insuficiente;
- operação com quantidade zero quando válida;
- TAG sem envio;
- item de estoque que não participa do inventário.

## Checklist

- finalização com conciliação correta;
- bloqueio com pendências;
- equipamentos não retornados;
- TAGs parcialmente usadas;
- TAGs sem uso;
- itens não enviados;
- materiais reutilizáveis;
- checklist já finalizado.

## Transferências

- transições válidas;
- transições inválidas;
- divergências;
- não recebidos;
- cancelamento;
- histórico;
- permissões por Base.

## Inventários

- inventário diurno;
- inventário noturno;
- inventário atravessando meia-noite;
- duração baseada em timestamps reais;
- filtros por Base e empresa.

---

# 10. COMANDOS DE VALIDAÇÃO

Rodar após cada fase:

```bash
python manage.py check
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
python manage.py test
```

Se houver pytest configurado:

```bash
pytest
```

Também executar:

```bash
ruff check .
```

E, se disponível:

```bash
coverage run manage.py test
coverage report
```

---

# 11. ESTRATÉGIA DE COMMITS

Sugestão de commits separados:

```text
chore: cria snapshot antes do hardening
security: remove credenciais e ajusta settings
security: protege endpoints e APIs financeiras
fix: corrige decorators de autorização
test: adiciona testes de permissões
fix: consolida estados de empréstimos
fix: consolida estados de transferências
perf: otimiza cálculo do estoque de insumos
refactor: separa views de insumos
refactor: extrai importador de inventários
chore: remove código legado confirmado
chore: reduz dependências sem uso
```

Não misturar:

- segurança;
- migrations;
- refatoração;
- limpeza;
- alteração visual;

no mesmo commit.

---

# 12. CRITÉRIOS PARA ABRIR O PULL REQUEST

O PR deve incluir:

1. resumo das mudanças;
2. riscos conhecidos;
3. arquivos afetados;
4. migrations criadas;
5. testes executados;
6. resultado do `check --deploy`;
7. plano de rollback;
8. comparação antes/depois;
9. confirmação de que o comportamento funcional foi preservado;
10. lista de itens não alterados deliberadamente.

O PR deve permanecer como **draft** até revisão manual.

---

# 13. ORDEM RECOMENDADA

## Etapa 1 — sem migrations

- snapshot;
- backup;
- settings;
- secrets;
- logs;
- autenticação;
- permissões;
- decorators;
- testes de segurança.

## Etapa 2 — correções pequenas

- `__str__`;
- URLs nomeadas;
- imports duplicados;
- ajustes sem mudança estrutural.

## Etapa 3 — inconsistências de status

- mapear dados;
- criar migrations de dados;
- consolidar estados;
- testar os fluxos completos.

## Etapa 4 — desempenho

- otimizar agregações;
- medir quantidade de queries;
- comparar resultado atual e otimizado.

## Etapa 5 — refatoração

- dividir views;
- extrair importadores;
- centralizar acesso.

## Etapa 6 — limpeza

- remover apenas código comprovadamente sem uso;
- remover dependências confirmadas;
- documentar descartes.

---

# 14. RESULTADO ESPERADO

Ao final desta etapa primária, o sistema deve:

- continuar funcionando como atualmente;
- possuir snapshot e rollback garantidos;
- não expor credenciais;
- operar com `DEBUG=False` em produção;
- proteger corretamente dados financeiros;
- reforçar o isolamento por empresa e Base;
- reduzir consultas excessivas;
- possuir testes para os fluxos críticos;
- identificar com segurança o código que pode ser descartado;
- estar preparado para as próximas evoluções do projeto.

---

# AVISO FINAL AO CODEX

Este sistema está funcionando bem no estado atual.

Portanto:

> Não reescrever fluxos funcionais apenas por preferência arquitetural.

Toda alteração deve ser justificada por:

- falha de segurança;
- bug comprovado;
- inconsistência confirmada;
- gargalo medido;
- código sem uso comprovado;
- melhoria com teste de regressão.

Antes de qualquer alteração estrutural, preservar o estado atual por snapshot, backup e branch exclusiva.
