# Etapa 17 — Compras, Catálogo, O.S. e Preços

## Estado: concluída

Os módulos de Compras, Catálogo, Ordens de Serviço e formação de preços agora
separam o cadastro técnico compartilhável da configuração operacional e
financeira de cada empresa. Permissão funcional e escopo de tenant continuam
sendo decisões independentes.

## Fronteiras dos dados

| Domínio | Escopo | Regra |
| --- | --- | --- |
| Empresa e Base | Tenant | A empresa delimita o tenant; Gestores e Operadores continuam limitados às Bases vinculadas. |
| Produto técnico | Plataforma ou empresa de origem | Produto sem empresa de origem é um item técnico global da plataforma. Produto criado por Admin comum pertence à empresa autorizada e não aparece para outros tenants. |
| Catálogo de produtos | Empresa | `CatalogoProdutoEmpresa` define se o produto está ativo, o preço, a fonte, o fornecedor e a validação em cada empresa. |
| Categoria | Empresa por meio do catálogo | A categoria é livre. Cada empresa define as categorias relevantes ao habilitar ou criar seus próprios produtos; filtros são derivados apenas do catálogo visível. |
| Equipamento | Base/empresa | O equipamento usa o preço do catálogo da empresa de sua Base. |
| Fornecedor | Plataforma | O cadastro jurídico/canônico do fornecedor não é duplicado e somente o Superuser pode alterá-lo. |
| Cotação de fornecedor | Empresa | Preço, validade, escolha e aplicação da cotação pertencem a uma empresa específica. |
| Pesquisa de preço on-line | Empresa | Pesquisa, ofertas e aplicação de resultados são isoladas pela empresa selecionada. |
| Aquisição e remessa | Empresa | Listagem, edição, aprovação, documentos e itens são resolvidos em querysets previamente filtrados. |
| Ordem de Serviço | Empresa/Base | Visualização e ações exigem capability exata e escopo sobre a empresa ou Base da O.S. |
| Custos de insumos | Base/empresa | A aplicação de uma cotação altera somente os saldos da empresa correspondente; não altera o preço global do insumo. |

## Regras de acesso

- somente o Superuser possui visão global da plataforma;
- Admin acessa integralmente a própria empresa;
- empresas adicionais exigem autorização explícita no perfil e capability da
  ação executada;
- Inventory Brasil, Inventory LATAM e OXXO não recebem compartilhamento
  automático: cada combinação de acesso do Admin permanece explícita;
- Admin de Inventory Brasil não vê outras empresas cadastradas, como Antropic,
  salvo autorização explícita concedida pelo Superuser;
- Admin de empresa externa ao grupo Inventory pode criar categorias e produtos
  privados e configurar seu próprio catálogo;
- um produto privado de outra empresa não aparece nos formulários de cadastro,
  catálogo ou aquisição;
- IDs externos de produto, aquisição, documento, cotação, pesquisa, oferta e
  Ordem de Serviço são validados dentro do queryset autorizado;
- permissão de visualização não concede automaticamente edição, aprovação,
  exportação ou administração financeira;
- a exceção do usuário de suporte permanece restrita a Chamados e não amplia
  Compras, Catálogo, Preços ou Ordens de Serviço.

## Compatibilidade e dados legados

As migrações preservam os dados existentes e criam configurações por empresa a
partir de equipamentos, aquisições e códigos já identificáveis. O preço global
legado do produto é usado somente como valor inicial de compatibilidade quando
uma configuração por empresa ainda não existe; depois disso, as alterações são
isoladas no catálogo do tenant.

Registros históricos, cotações ou pesquisas legadas cuja empresa não pôde ser
determinada permanecem com tenant nulo como dados de plataforma. Eles não são
listados para usuários comuns. O histórico de preço de produto não possui rota
de consulta pública e é utilizado apenas pelo serviço interno de atualização.

## Migrações

- `estoque.0048_produto_categoria_e_origem_empresa`;
- `compras.0003_catalogoprodutoempresa`;
- `insumos.0036_precos_e_pesquisas_por_empresa`.

## Validação

- `manage.py check`: sem problemas;
- `makemigrations --check --dry-run`: nenhuma alteração pendente;
- 87 testes integrados de Compras, Catálogo, Preços, O.S. e contratos de tenant:
  aprovados;
- teste de orçamento de consultas do contexto multi-tenant: aprovado;
- migrações aplicadas no banco de desenvolvimento;
- auditoria pós-migração: 37 configurações de catálogo ativas e 13 produtos com
  empresa de origem identificada;
- somente o usuário `admin` permanece como Superuser;
- nenhuma senha foi modificada por esta etapa.
