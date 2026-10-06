# R1.H — Release Gate de Chips / Linhas Móveis

## Resultado

Revisão concluída em 01/10/2026.

- models, constraints, policy e isolamento tenant validados;
- cadastro e edição de linha restritos a Admin/Superuser;
- usuário responsável opcional limitado à empresa e à Base da linha;
- vínculo, troca e desvínculo disponíveis na edição do equipamento elegível;
- ICCID mascarado e PIN/PUK ausentes de APIs, Tory, exports e notificações;
- empresa inativa falha fechada;
- migration aditiva `0061_linhamovel_usuario_responsavel` validada;
- `manage.py check` sem ocorrências;
- `makemigrations --check --dry-run` sem alterações pendentes;
- gate específico aprovado com 85 testes;
- suíte completa executada com 694 testes: 693 passaram e a única expectativa
  desatualizada do card vazio do dashboard foi corrigida e revalidada em sua
  suíte (9/9), junto dos fluxos impactados.

## Configuração obrigatória de PIN/PUK

PIN/PUK permanecem indisponíveis até que a variável abaixo seja configurada:

```text
LINHAS_MOVEIS_CREDENTIAL_KEYS=v1:<chave-fernet>
```

Gere a entrada explicitamente, sem alterar `SECRET_KEY`:

```text
python manage.py gerar_chave_credenciais_linhas
```

O comando apenas exibe a entrada; ele não altera `.env`, Render ou qualquer
senha. O valor deve ser armazenado como secret no ambiente local e no Render.

## Deploy

O `build.sh` já executa `python manage.py migrate`. Portanto, o deploy que
contiver a migration `0061` cria `usuario_responsavel_id` antes de iniciar a
nova versão da aplicação.

Ordem operacional:

1. configurar `LINHAS_MOVEIS_CREDENTIAL_KEYS` como secret;
2. publicar o código e as migrations da R1;
3. confirmar `Applying estoque.0061... OK` no build;
4. abrir `/linhas-moveis/` como Admin;
5. cadastrar uma linha de homologação, atribuir um responsável e vinculá-la a
   um equipamento elegível da mesma Base;
6. cadastrar e consultar PIN/PUK somente com a permissão dedicada.

## Rotação da chave

Para rotacionar sem perder leitura:

1. gerar uma nova entrada, por exemplo `v2:<nova-chave>`;
2. configurar `LINHAS_MOVEIS_CREDENTIAL_KEYS=v2:<nova>,v1:<anterior>`;
3. manter a chave anterior durante a transição;
4. salvar novamente as credenciais existentes para cifrá-las com `v2`;
5. verificar que não existem registros com `chave_id=v1`;
6. somente então remover a chave anterior do secret.

Nunca registrar, versionar ou enviar os valores das chaves em logs ou tickets.

