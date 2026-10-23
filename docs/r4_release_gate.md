# Release Gate R4 — Catálogo e novos ativos

## Status

**PRONTO PARA DEPLOY CONTROLADO**, pendente de autorização explícita do usuário.

O código da R5 não foi iniciado.

## Escopo concluído

- capacidades de ativos configuráveis por produto e empresa;
- comportamento legado preservado quando não há configuração explícita;
- série e patrimônio opcionais ou obrigatórios conforme o catálogo do tenant;
- unicidade preservada quando os identificadores são informados;
- observação operacional por unidade individualizada;
- suporte a IMEI 1 e IMEI 2, ambos opcionais;
- validação de 15 dígitos e bloqueio de repetição de IMEI nos fluxos de cadastro
  e edição;
- exibição de IMEI e observação no estoque;
- histórico de criação e edição com os novos identificadores;
- contrato legado da API `produtos-por-categoria` preservado; capacidades são
  retornadas em um mapa adicional;
- isolamento validado: o mesmo produto pode ter capacidades diferentes em
  empresas distintas.

## Arquivos alterados

- `compras/models.py`
- `compras/forms.py`
- `compras/views.py`
- `compras/templates/compras/catalogo_empresa.html`
- `estoque/models.py`
- `estoque/forms.py`
- `estoque/views.py`
- `estoque/services/ativo_capacidade_service.py`
- `estoque/templates/estoque/cadastrar_equipamento.html`
- `estoque/templates/estoque/editar_equipamento.html`
- `estoque/templates/estoque/estoque.html`
- `estoque/test_capacidades_ativos_r4.py`
- documentação R4.

## Migrations

### `estoque.0072_equipamento_identificadores_flexiveis`

- torna `numero_serie` e `patrimonio` anuláveis;
- mantém `unique=True` para valores informados;
- converte somente strings vazias em `NULL`;
- adiciona `observacao_operacional`.

Nenhum patrimônio ou número de série preenchido é apagado.

### `estoque.0073_equipamento_imeis`

- adiciona `imei_1` e `imei_2` como campos opcionais, anuláveis e únicos em
  seus respectivos slots;
- não altera registros existentes.

## Testes e checks

- 103 testes direcionados, de regressão e multi-tenant: aprovados;
- 33 testes completos do app `compras`: aprovados;
- 571 testes do app `estoque` percorreram sem marcador de falha usando execução
  paralela; no Windows, o invólucro do comando não encerrou após os workers já
  terem terminado e não imprimiu o resumo final;
- `python manage.py check`: aprovado;
- `python manage.py makemigrations --check --dry-run`: aprovado;
- `git diff --check`: aprovado;
- migrations `0072` e `0073` aplicadas com sucesso em bancos SQLite limpos
  durante todas as suítes.

## Riscos conhecidos

1. A alteração de nulabilidade das colunas pode obter lock breve na tabela
   `estoque_equipamento` durante a migration no PostgreSQL.
2. A unicidade de cada slot de IMEI é protegida no banco. A proibição de usar
   um valor de `imei_1` como `imei_2` de outra unidade é validada pela aplicação;
   duas requisições concorrentes extremamente próximas ainda representam uma
   janela residual. O sistema é operacional interno e os formulários normais
   bloqueiam esse caso.
3. Templates e comportamento dinâmico devem receber smoke test no navegador
   após o deploy.
4. A suíte ampliada do app `estoque` encontrou uma limitação de encerramento do
   runner no ambiente Windows/sandbox depois de todos os workers finalizarem;
   não houve marcador `E` ou `F` nessa repetição.

## Passos de deploy

1. Criar snapshot/backup atual do PostgreSQL no Render.
2. Confirmar que não existe migration em execução nem cadastro em lote ativo.
3. Publicar a revisão autorizada da branch `main`.
4. No ambiente de produção, executar:

   ```text
   python manage.py migrate --plan
   python manage.py migrate --noinput
   python manage.py check --deploy
   ```

5. Reiniciar o serviço somente após a migration concluir.

## Validação pós-deploy

1. Confirmar no Render que `0072` e `0073` aparecem aplicadas.
2. Entrar como Admin e abrir o catálogo da própria empresa.
3. Configurar um produto sem série obrigatória e validar cadastro sem série.
4. Validar que um produto legado continua exigindo série e patrimônio.
5. Habilitar IMEI para um modelo de celular e cadastrar:
   - sem IMEI;
   - somente com IMEI 1;
   - com IMEI 1 e IMEI 2.
6. Confirmar bloqueio de IMEI duplicado e de valor com tamanho inválido.
7. Confirmar que o estoque mostra os identificadores pertinentes.
8. Confirmar que outra empresa não vê nem herda a configuração realizada.
9. Confirmar que Gestor mantém seu escopo por Base e que Operador não recebe
   acesso administrativo ao catálogo.
10. Verificar logs de erro do Render após os testes.

## Rollback/recuperação

- preferir rollback do código para a revisão anterior, mantendo as colunas
  novas no banco; elas são compatíveis e inofensivas para o código anterior;
- não reverter `0072` depois que houver ativos sem série/patrimônio, pois o
  schema anterior não aceita esses registros;
- não reverter `0073` depois que IMEIs forem cadastrados, para não perder os
  valores;
- em falha de migration, interromper o deploy, preservar logs e restaurar o
  snapshot somente se a correção forward não for segura.

## STOP

Não executar push, deploy, rollback ou iniciar R5 sem nova autorização.
