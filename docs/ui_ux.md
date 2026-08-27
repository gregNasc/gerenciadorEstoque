# Padrões de UI/UX

Este documento registra os padrões visuais oficiais do `gerenciadorEstoque`.
As telas continuam baseadas em Bootstrap 5, Bootstrap Icons e templates Django.

## Componentes globais

- `app-page-header`: título, descrição, contexto e ações da página.
- `app-section-header`: título e ações de uma seção interna.
- `app-filter-panel`: filtros com ações explícitas de aplicar e limpar.
- `app-kpi-card`: indicador resumido; quando interativo deve ser um `button` ou possuir suporte completo a teclado.
- `app-status`: estado textual com variantes `success`, `warning`, `danger`, `info` e `neutral`.
- `app-empty-state`: ausência de resultados com mensagem curta e ação apenas quando útil.
- `app-action-toolbar`: ações secundárias, exportação e controles rápidos.
- `app-loading`: spinner pequeno acompanhado do texto “Carregando...”.

Cards estáticos não recebem elevação no hover. Cor nunca é o único meio de
comunicar um estado.

## Navegação

A navegação principal usa sidebar recolhível no desktop e gaveta com backdrop
em telas menores. Os mesmos testes de permissão que controlavam a navbar
continuam controlando cada item. O perfil fica na topbar e reúne Preferências
de comunicação e Sair.

## Modais

Bootstrap Modal é o padrão preferencial para novos componentes. Todo modal
novo deve possuir título, botão Fechar, `aria-labelledby`, backdrop, Escape,
controle de foco e retorno de foco. Componentes legados devem ser migrados
gradualmente, sem alterar seus fluxos funcionais.

## Glossário

- **Inventário**: operação planejada de contagem em uma loja ou unidade.
- **Base**: unidade operacional responsável pelos recursos.
- **Regional**: agrupamento ou referência operacional de bases.
- **Equipamento**: ativo controlado individualmente.
- **Insumo**: material consumível ou reutilizável controlado em quantidade.
- **Checklist**: registro de envio, uso, retorno e conciliação de uma operação.
- **Chamado**: solicitação de suporte vinculada ao contexto operacional.
- **Atendente**: usuário responsável pelo atendimento do chamado.
- **SICK**: fluxo de indisponibilidade, avaliação e manutenção de equipamentos.
- **Ordem de Serviço (O.S.)**: registro formal de execução de serviço.
- **Auditoria**: conferência controlada dos equipamentos de uma base.
- **Transferência**: movimentação definitiva entre bases.
- **Empréstimo**: movimentação temporária com devolução prevista.

Usar “Inventory” apenas quando for nome próprio de sistema, empresa ou conceito
externo oficial. Nos demais textos da interface, usar “Inventário”.

## Alertas de chamados

Novas ocorrências de outros usuários emitem som inclusive quando a conversa do
chamado está aberta. Eventos repetidos continuam deduplicados. Como exigido
pelos navegadores, a página precisa receber ao menos uma interação do usuário
na sessão para liberar reprodução de áudio.
