# Adicional G.3 — Terminologia no onboarding (27/09/2026)

A etapa de Terminologia do onboarding agora permite configurar:

- o nome exibido de cada módulo habilitado;
- singular e plural dos termos gerais pertinentes aos módulos escolhidos.

O backend aceita somente módulos efetivamente habilitados e chaves previstas em
`TermoEmpresa.Chave`. Um POST manual não consegue criar chaves arbitrárias nem
personalizar recursos desabilitados.

Valores vazios mantêm os nomes padrão. Quando uma personalização existente é
apagada, seu registro também é removido com segurança. Toda a gravação ocorre em
transação única; um valor inválido impede alterações parciais.

As personalizações afetam somente a apresentação. Códigos técnicos, URLs,
permissões e regras de autorização permanecem inalterados.
