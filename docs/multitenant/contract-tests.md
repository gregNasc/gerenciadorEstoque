# Etapa 4 — Testes de contrato multi-tenant

Data do checkpoint: 2026-09-05.

## Objetivo

Registrar em testes automatizados o isolamento e as exceções de visibilidade
esperados antes das mudanças estruturais do modelo multi-tenant.

Os testes usam `Empresa` como tenant e exercitam a camada existente
`secure_queryset()` sobre equipamentos, cuja empresa é determinada pela rota
`Equipamento -> Base -> Empresa`.

## Cenário criado

O cenário isolado de teste contém:

- Empresa A;
- Empresa B;
- Inventory Brasil;
- Inventory LATAM;
- OXXO;
- um equipamento em uma base de cada empresa;
- Superuser;
- Admin Empresa A;
- Admin Empresa B;
- Admin Inventory Brasil;
- Admin Inventory LATAM;
- Admin OXXO;
- Gestor vinculado à Empresa A e à sua base;
- Operador vinculado à Empresa A e à sua base.

Os nomes existem apenas como rótulos das fixtures. Nenhuma autorização é
concedida por nome, username ou ID fixo.

## Decisão de negócio confirmada

O role Admin tem acesso administrativo integral ao sistema dentro das empresas
que compõem seu escopo autorizado. Ele não recebe, por isso, poderes estruturais
da plataforma reservados ao `is_superuser`.

O escopo administrativo requerido é:

- Admin de uma empresa comum: somente a própria empresa;
- Admin Inventory Brasil: Inventory Brasil, Inventory LATAM e OXXO;
- Admin Inventory LATAM: somente Inventory LATAM;
- Admin OXXO: somente OXXO.

Gestores e Operadores continuam vinculados às Bases autorizadas. A Etapa 4 fixa
o contrato de visibilidade sobre a rota de ownership dos equipamentos. A mesma
regra deverá ser aplicada aos demais módulos nas etapas de isolamento por
domínio.

## Contratos registrados

| Contrato | Estado na Etapa 4 |
|---|---|
| Superuser atravessa tenants | falha esperada |
| Admin Empresa A vê somente Empresa A | falha esperada |
| Admin Empresa B vê somente Empresa B | falha esperada |
| Admin Inventory Brasil vê Inventory Brasil e Inventory LATAM, sem Empresa A/B | falha esperada |
| Admin Inventory Brasil vê Inventory Brasil e OXXO, sem Empresa A/B | falha esperada |
| Admin Inventory LATAM não recebe acesso inverso | falha esperada |
| Admin OXXO não recebe acesso inverso | falha esperada |
| Gestor não atravessa tenant e fica limitado à sua base autorizada | ativo e passando |
| Operador não atravessa tenant e fica limitado à sua base autorizada | ativo e passando |

## Estratégia de ativação progressiva

Os sete contratos ainda incompatíveis com a arquitetura atual usam
`unittest.expectedFailure`. Isso preserva uma suíte verde sem esconder o estado
real: quando uma etapa implementar a regra correspondente, o sucesso inesperado
faz o teste sinalizar que o marcador deve ser removido.

A fixture de Admin usa atualização direta do registro de `Perfil` apenas no
banco de teste. Isso permite representar o estado futuro `Admin + Empresa`
enquanto `Perfil.save()` ainda remove a empresa de perfis Admin.

## Resultado

Comando específico:

```powershell
python manage.py test estoque.test_multitenant_contract --keepdb -v 2
```

Resultado: 9 testes executados, 2 aprovados e 7 falhas esperadas; suíte OK.

Regressão diretamente relacionada:

```powershell
python manage.py test estoque.test_multitenant_contract estoque.test_user_access_profiles --keepdb -v 1
```

Resultado: 16 testes executados, 9 aprovados e 7 falhas esperadas; suíte OK.

Validações estruturais:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
```

Resultado: nenhuma inconsistência e nenhuma alteração de model sem migration.

Também foi executada a suíte completa do app `estoque`: 169 testes, com 160
aprovados, 7 falhas esperadas do contrato e 2 falhas em testes antigos de UI:

- `FluxoSickTests.test_indice_abre_detalhes_com_classe_show_e_botao_mobile`
  espera um trecho JavaScript que não está mais no HTML renderizado e também
  falha quando executado isoladamente;
- `UIConsolidationTests.test_navegacao_recolhe_sidebar_no_desktop_e_fecha_no_mobile`
  falhou somente na suíte completa, mas passou isoladamente e também passou
  quando executado logo após todos os novos testes de contrato, caracterizando
  dependência de ordem/estado fora da Etapa 4.

Esta etapa não altera models, regras de autorização em runtime nem dados de
produção e não cria migration.
