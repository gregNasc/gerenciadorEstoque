# Adicional G.7 — Revisão final e ativação do tenant

## Status

Concluído.

## Revisão final

A décima etapa do onboarding agora apresenta, antes da ativação:

- identidade e slug da empresa;
- primeiro Admin ativo;
- módulos habilitados com seus nomes de apresentação;
- módulos desabilitados;
- terminologia resolvida, com indicação de termos personalizados;
- categorias ativas e quantidade de categorias inativas;
- produtos ativos e visíveis no catálogo do tenant;
- seções documentais habilitadas e seus nomes personalizados;
- bases iniciais;
- relacionamentos opcionais ativos com empresas ativas;
- indicação de compartilhamento de suporte.

Categorias, produtos, bases e relacionamentos continuam opcionais. Seus estados vazios são apresentados explicitamente na revisão.

## Validação antes da ativação

O botão de ativação somente fica disponível quando:

- todos os módulos ativos do catálogo foram revisados explicitamente;
- pelo menos um módulo está habilitado;
- existe um Admin ativo, não Superuser, vinculado ao tenant;
- quando Documentação está habilitada, todas as seis seções foram revisadas e pelo menos uma está habilitada.

O backend repete todas as verificações no `POST`. Alterar o HTML ou enviar a requisição manualmente não contorna a validação.

## Fluxo e interface

- A numeração visual foi atualizada para as dez etapas reais.
- Os links de retorno de Primeiro Admin, Bases, Relacionamentos e Revisão foram corrigidos.
- A revisão informa todas as pendências sem ativar parcialmente a empresa.
- A empresa permanece inativa até a validação final bem-sucedida.
- Nenhuma senha ou `SECRET_KEY` foi alterada.

## Validação

- `manage.py check`: aprovado.
- Testes focados do onboarding: 21 aprovados.
- Suíte relacionada de onboarding e isolamento tenant: 57 aprovados.
- Suíte completa: 615 testes aprovados em 723,379 segundos.

## Próximo incremento

Adicional H — manutenção posterior das configurações pelo Painel Superuser.
