# Adicional G.5 — Catálogo no onboarding

## Status

Concluído.

## Implementação

- A etapa `catalogo` deixou de ser apenas informativa.
- O Superuser pode cadastrar até 25 produtos próprios por envio.
- Todo produto criado nessa etapa recebe obrigatoriamente:
  - `empresa_catalogo_origem` igual ao tenant em onboarding;
  - `criado_por` igual ao Superuser responsável;
  - vínculo ativo em `CatalogoProdutoEmpresa` para o tenant.
- Código, descrição, fabricante, modelo e categoria são validados no backend.
- A categoria precisa estar ativa e pertencer ao tenant atual.
- Produtos existentes somente entram no catálogo quando selecionados explicitamente.
- A lista de compartilhamento contém apenas produtos ativos compatíveis com as categorias ativas do tenant.
- Produtos não selecionados não são herdados nem vinculados automaticamente.
- Um catálogo vazio continua sendo uma configuração válida.
- Ao desmarcar um item, o vínculo é desativado sem excluir o produto ou o histórico.
- Envios sem o marcador da nova interface preservam compatibilidade e não alteram o catálogo.

## Segurança multi-tenant

- A rota permanece exclusiva de Superuser.
- Identificadores adulterados, produtos inativos e categorias incompatíveis são rejeitados.
- A gravação é atômica: qualquer erro impede criação ou compartilhamento parcial.
- Não existe fallback para catálogo global.
- Nenhuma senha ou `SECRET_KEY` foi alterada.

## Validação

- `manage.py check`: aprovado.
- `makemigrations --check --dry-run`: nenhuma alteração detectada.
- Testes focados do onboarding: 15 aprovados.
- Testes de regressão de catálogo e isolamento: 23 aprovados.
- Suíte completa: 607 testes aprovados em 701,319 segundos.

## Próximo incremento

Adicional G.6 — configuração real das seções de documentação no onboarding.
