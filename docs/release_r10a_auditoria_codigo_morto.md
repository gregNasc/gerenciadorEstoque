# R10.A — Auditoria inicial de código morto

**Data:** 06/11/2026  
**Status:** CONCLUÍDA — inventário e classificação preliminar  
**Alterações de dados ou schema:** nenhuma  
**Arquivos removidos:** nenhum

## Objetivo

Iniciar a higienização pré-AWS sem apagar código apenas por aparência. Esta
subetapa mapeia candidatos e registra a evidência necessária para que cada
remoção futura tenha teste dirigido e rollback por Git.

A R9/TOTVS permanece pausada por dependência da equipe Financeira. Sua fundação
continua desativada e isolada; a auditoria da R10 não altera o contrato futuro
da integração.

## Baseline inventariado

| Área | Quantidade observada |
| --- | ---: |
| Arquivos Python | 540 |
| Templates HTML | 140 |
| JavaScript | 6 |
| CSS | 3 |
| Migrations históricas | 175 |
| Comandos de gerenciamento | 29 |
| Declarações de rota ativas, por linha | 240 |

Distribuição das rotas ativas observadas:

| Módulo | Rotas |
| --- | ---: |
| `estoque` | 104 |
| `insumos` | 49 |
| `compras` | 25 |
| `auditorias` | 24 |
| `chamados` | 13 |
| `integracao` | 6 |
| `ordens_servico` | 6 |
| projeto Django | 13 |

As contagens orientam o trabalho, mas não provam uso ou desuso isoladamente.
Rotas dinâmicas, templates carregados por convenção, e-mails, jobs e integrações
externas ainda precisam de verificação específica.

## Classificação: MANTER

| Item | Evidência |
| --- | --- |
| 175 migrations históricas | O plano proíbe apagar migrations aplicadas. Eventual squash será atividade própria. |
| CSS `style.css`, `tory.css` e `dashboard-ativos.css` | Referenciados por `base.html` ou `index.html` e cobertos por testes de interface. |
| JS `tory-api.js`, `tory-renderer.js`, `tory-resultados.js` e `tory.js` | Carregados explicitamente por `base.html`; existem testes de interface da Tory. |
| `estoque/transferencia/selecionados.html` | Renderizado pela view ativa `transferencia_selecionados`. Não confundir com o template legado `estoque/selecionados.html`. |
| Comandos de comunicação, CAEPI, Planning e diagnóstico | Podem ser executados por worker, Shell ou agendamento e não podem ser classificados apenas por ausência de import Python. |
| Fundação TOTVS | Mantida desativada para retomada após a documentação da API. |

## Classificação: MIGRAR

| Item | Motivo | Condição antes da mudança |
| --- | --- | --- |
| Quatro arquivos em `equipamentos/` na raiz | O diretório não é app Django e contém imagens com aparência de uploads; o model grava em `media/equipamentos/`. | Comparar nomes com o banco e o armazenamento de produção, preservar cópia e só então retirar do Git. |
| `scripts/extract_manual_text.py` | É uma ferramenta de preparação de conteúdo, não parte do runtime. Importa `pypdf`, que não está declarado diretamente em `requirements.txt`. | Decidir se vira comando documentado de desenvolvimento ou se será arquivado; testar a geração dos textos antes. |

## Classificação: REMOVER — candidatos, ainda não executados

Os itens abaixo possuem evidência estática forte, mas serão removidos apenas em
patches pequenos e acompanhados de testes.

| Item | Evidência atual | Teste obrigatório antes/depois |
| --- | --- | --- |
| `.idea/` versionado | Sete arquivos específicos do IDE, sem função no build ou runtime. | Instalação e execução em checkout limpo. A pasta local do desenvolvedor não precisa ser apagada. |
| `estoque/static/images/white-gradient-background-modern-design.zip` | ZIP de aproximadamente 8,5 MB sem referência no código ou templates. | `collectstatic`, login e páginas principais. |
| `estoque/templates/script.js` | Script dentro da pasta de templates, sem inclusão encontrada; existe JS real em `estoque/static/js/`. | Dashboard e animações de cards. |
| `estoque/templates/registration/password_reset_email.html` | Reset ativo usa `estoque_password_reset_email.txt`; nenhuma referência exata ao HTML foi encontrada. | Fluxo completo de recuperação de senha com backend de e-mail de teste. |
| `insumos/templates/insumos/dashboard/financeiro/dashboard_financeiro.html` | A rota financeira chama `dashboard_custos`, que renderiza `insumos/custos/dashboard_custos.html`. | Acesso com perfil Financeiro e bloqueio de perfis sem permissão. |
| `insumos/templates/insumos/dashboard.html` | Nenhuma renderização, extensão ou inclusão exata encontrada; dashboards atuais são separados por finalidade. | Dashboards base, saúde, planejamento e financeiro. |
| `estoque/templates/estoque/lista_transferencias.html` | A lista ativa renderiza `estoque/transferencia/listar.html`. | Lista, filtros e permissões de transferências. |
| `estoque/templates/estoque/movimentar_estoque.html` | Nenhuma rota, view ou renderização encontrada. | Cadastro, edição e movimentação pelos fluxos ativos. |
| `estoque/templates/estoque/selecionados.html` | Nenhuma referência; o fluxo ativo usa `estoque/transferencia/selecionados.html`. | Detalhe e separação de transferência. |
| `estoque/templates/estoque/solicitar.html` | Nenhuma referência; solicitações atuais possuem templates próprios. | Criação e listagem de solicitações. |
| `estoque/templates/estoque/emprestimos/adicionar_itens.html` | A rota histórica de adicionar itens está comentada e não há renderização encontrada. | Criação, recebimento, devolução e detalhe de empréstimo. |
| `estoque/templates/estoque/transferencia/criar.html` | A rota histórica de criação está comentada e não há renderização encontrada. | Criação operacional vigente e transferências em lote. |
| `estoque/templates/estoque/detalhes_produto.html` e `detalhes_produto_view` | A view antiga não está roteada e termina sem resposta para GET. A rota ativa usa `detalhes_produto`, que retorna JSON para o modal; o template antigo usa assinatura de URL incompatível com a rota atual. | Modal de produto, isolamento por empresa/Base, auditoria e transferências abertas. |

## Classificação: DÚVIDA

| Item | Por que ainda não remover |
| --- | --- |
| `estoque/static/images/estoque1.jpg` | Sem referência encontrada, mas pode ter sido preservado como alternativa visual. Confirmar com inspeção e histórico. |
| Dependências como `altair`, `anthropic`, `numpy`, `pandas`, `pyarrow`, `pydeck`, `streamlit`, `matplotlib`, `pydantic`, `GitPython`, `antiorm`, `db`, `db-sqlite3`, `npm` e pacotes Django auxiliares | Não foram encontradas referências diretas no Python da aplicação. Algumas podem ser transitivas, ferramentas locais ou resquícios do ambiente que originou o `requirements.txt`. A remoção exige árvore de dependências, instalação limpa e suíte completa. |
| Arquivos estáticos de manuais e documentação | O acesso pode ocorrer por catálogo JSON, e não por referência textual direta. Manter até auditar `manuais.json`, `documentacao.json` e variantes em espanhol. |
| Models legados identificados em documentos anteriores | Models podem preservar histórico ou integrações. A ausência de rota não autoriza apagar tabela ou migration. |

## Resíduos locais não versionados

Diretórios como `__pycache__`, `.codex_tmp`, `backups`, `output`, `outputs`,
`staticfiles`, `media` e `private_media` já estão ignorados. Os diretórios
`.test-tmp-r4` e `.test-tmp-r5` não estão versionados, mas ainda não possuem
regra explícita no `.gitignore`; serão tratados em patch separado.

## Riscos encontrados

1. Remover templates em lote pode ocultar dependências carregadas por nome
   dinâmico; cada grupo deverá ter busca e teste próprios.
2. O `requirements.txt` aparenta conter pacotes de um ambiente mais amplo que o
   runtime Django. Uma limpeza sem instalação do zero pode quebrar o build.
3. Imagens na raiz podem ser cópias de uploads reais. Não apagar antes de
   comparar banco, Render e futuro armazenamento S3.
4. A redução do repositório pode melhorar build e deploy, mas desempenho não
   será usado como justificativa para remover arquivos sem prova.

## Próxima subetapa segura — R10.B

Executar o primeiro patch reversível, limitado a higiene de versionamento e
artefatos comprovadamente não executáveis:

1. adicionar `.idea/` e `.test-tmp-*/` ao `.gitignore`;
2. retirar `.idea/` apenas do versionamento, preservando a pasta local;
3. auditar hash e histórico do ZIP estático antes de removê-lo;
4. validar `manage.py check`, `collectstatic` e testes de login/dashboard;
5. parar e apresentar o resultado antes de tocar em templates ou dependências.

Nenhuma remoção desta lista está autorizada implicitamente por este relatório.
