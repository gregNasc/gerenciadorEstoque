# Release Gate R2 — Custódia, documentos e assinatura

Data da avaliação local: 09 e 13/10/2026.

## Resultado

**Gate técnico local: aprovado.** O escopo R2.A–R2.L está implementado, os
810 testes da regressão particionada passam, as migrations foram aplicadas do
zero e a migration final foi revertida e reaplicada com sucesso em banco
temporário.

**Liberação de produção: pendente de homologação externa e autorização.** O
código não foi implantado. DocuSign, testemunha real do RH, SMTP e WhatsApp não
foram acionados com contas reais durante esta avaliação.

## Escopo funcional

| Item do gate | Resultado | Evidência |
| --- | --- | --- |
| Colaborador sem `User`, vínculo opcional e isolamento | Aprovado localmente | `estoque/test_colaboradores_r2a.py` |
| Local Físico tenant-aware e compartilhamento autorizado | Aprovado localmente | `estoque/test_locais_fisicos_r2b.py` |
| Elegibilidade explícita, inclusive chip/linha; balança recusada | Aprovado localmente | `estoque/test_custodia_elegibilidade_r2c.py` |
| Custódia e isolamento | Aprovado localmente | `estoque/test_custodia_modelo_r2d.py` |
| Múltiplos itens e snapshots reais | Aprovado localmente | `estoque/test_itens_custodia_r2e.py` |
| Exclusividade do ativo vigente e histórico preservado | Aprovado localmente | `estoque/test_exclusividade_custodia_r2f.py` |
| Compatibilidade do responsável legado | Aprovado localmente | `estoque/test_responsavel_legado_custodia_r2g.py` |
| Devolução total/parcial e liberação do item | Aprovado localmente | `estoque/test_devolucao_custodia_r2h.py` |
| Termo de Entrega privado, imutável e não sobrescrito | Aprovado localmente | `estoque/test_termo_entrega_custodia_r2i.py` |
| Termo de Devolução separado | Aprovado localmente | `estoque/test_termo_devolucao_custodia_r2j.py` |
| Configuração DocuSign/RH por tenant | Aprovado com cliente simulado | `integracao/tests/test_docusign_r2k.py` |
| Webhook HMAC, idempotência e PDF assinado vinculado | Aprovado com cliente simulado | `integracao/tests/test_docusign_r2k.py` |
| Notificações internas, e-mail/WhatsApp por outbox | Aprovado localmente; canais reais pendentes | `estoque/test_notificacoes_custodia_r2l.py` |
| José sem acesso a preços | Aprovado | `ordens_servico/test_permissions_special.py` |
| Admin, Gestor e Operador preservados no escopo tenant | Aprovado nos testes direcionados | testes de políticas e isolamento dos módulos |
| Implementação parcial de EPI/R3 | Ausente | busca no escopo R2 encontrou apenas menção documental de exclusão |

## Migrations

Migrations da R2:

- `estoque.0063` a `estoque.0071`;
- `integracao.0005`.

Validação executada em SQLite limpo:

- cadeia completa aplicada com sucesso até `estoque.0071` e
  `integracao.0005`;
- `estoque.0071` revertida até `estoque.0070` com sucesso;
- `estoque.0071` reaplicada com sucesso;
- `makemigrations --check --dry-run`: nenhuma alteração detectada.

As migrations são majoritariamente aditivas. `estoque.0067` e
`estoque.0069` contêm preenchimento controlado de dados antes das constraints e
dos snapshots. O deploy deve executar `migrate --plan` contra uma cópia recente
do PostgreSQL antes de aplicar em produção.

## Testes e checks

- 124/124 testes direcionados R2.A–R2.L aprovados;
- 810/810 testes da regressão particionada aprovados:
  - `estoque`: 548/548;
  - `auditorias` e `chamados`: 83/83;
  - `integracao` e `ordens_servico`: 88/88;
  - `compras` e `insumos`: 91/91;
- os cinco testes ASGI/WebSocket foram executados fora da restrição local de
  sockets e também foram aprovados;
- `python manage.py check`: aprovado, zero problemas;
- `python manage.py check --deploy` com ambiente equivalente ao de produção:
  sem erros; permaneceu somente o aviso opcional `security.W021`, pois
  `SECURE_HSTS_PRELOAD` deve continuar desativado até a validação definitiva
  do domínio HTTPS;
- `python manage.py makemigrations --check --dry-run`: aprovado;
- `git diff --check`: aprovado; somente avisos de normalização LF/CRLF;
- carga inicial de insumos validada como idempotente também para descrições
  acentuadas no SQLite;
- notificação de manutenção validada com comparação determinística após a
  normalização obrigatória em caixa alta.

## Riscos e pendências externas

1. Confirmar que o plano DocuSign contratado permite eSignature API.
2. Criar aplicação de homologação, consentir o JWT e configurar os secrets fora
   do repositório.
3. Configurar o Connect/HMAC e validar envelope real, ordem colaborador → RH,
   webhook, PDF combinado e certificado.
4. Validar nome e e-mail da testemunha real do RH em cada tenant habilitado.
5. Garantir armazenamento privado e persistente para termos, PDFs assinados e
   certificados; o disco efêmero do serviço web não é suficiente.
6. Configurar `CHANNEL_REDIS_URL`; a aplicação falha fechada em produção
   quando o Redis de Channels não está definido.
7. Manter `SECURE_HSTS_PRELOAD=False` durante a homologação e avaliar sua
   ativação somente depois da validação definitiva do domínio HTTPS.
8. Homologar SMTP, remetente e DNS (SPF/DKIM/DMARC).
9. Aprovar os seis templates `custodia_*` na Meta e revisar consentimentos.
10. Configurar scheduler para `processar_notificacoes_custodia`.

## Deploy controlado

1. Obter autorização explícita e definir janela de manutenção.
2. Gerar backup verificável do PostgreSQL e do armazenamento privado.
3. Validar a release exata e preservar `SECRET_KEY` e credenciais existentes.
4. Configurar os secrets DocuSign descritos em `docs/r2k_docusign.md`, mantendo
   `DOCUSIGN_ENABLED=False` no primeiro deploy.
5. Configurar SMTP/WhatsApp conforme `docs/r2l_notificacoes_essenciais.md`,
   mantendo `CUSTODIA_EMAIL_ENABLED=False` e `WHATSAPP_ENABLED=False`.
6. Em uma cópia recente do PostgreSQL, executar:

   ```powershell
   python manage.py migrate --plan
   python manage.py migrate --noinput
   python manage.py check --deploy
   python manage.py collectstatic --noinput
   ```

7. Implantar a aplicação e executar as migrations em produção apenas na janela
   autorizada.
8. Fazer smoke test com Superuser, Admin, Gestor e Operador antes de habilitar
   qualquer integração externa.
9. Habilitar DocuSign primeiro em um tenant de homologação e executar um único
   envelope controlado.
10. Somente após a homologação do passo anterior, habilitar e-mail e WhatsApp
    gradualmente e ativar o scheduler da outbox.

## Validação pós-deploy

- `python manage.py showmigrations estoque integracao` mostra `estoque.0063` a
  `estoque.0071` e `integracao.0005` aplicadas;
- `python manage.py check` não apresenta problemas;
- login e navegação respeitam tenant e perfis;
- colaborador sem conta pode receber Custódia;
- equipamento e chip elegíveis entram em Custódia, enquanto item inelegível é
  recusado;
- não é possível manter o mesmo ativo em duas Custódias vigentes;
- devolução libera o item sem apagar o histórico;
- Termos de Entrega e Devolução são arquivos distintos, privados e preservados;
- envelope de homologação mantém ordem colaborador → RH;
- webhook inválido é recusado e repetição válida permanece idempotente;
- PDF assinado e certificado ficam vinculados ao envelope correto;
- falha de e-mail/WhatsApp não altera o estado oficial da Custódia;
- logs e registros persistidos não expõem tokens, chaves, PIN ou PUK.

## Rollback e recuperação

- primeiro desabilitar `DOCUSIGN_ENABLED`, `CUSTODIA_EMAIL_ENABLED` e
  `WHATSAPP_ENABLED`;
- interromper o scheduler da outbox;
- reverter a versão da aplicação para a release anterior;
- preferir manter as tabelas aditivas no banco durante o rollback da aplicação;
- não apagar termos, envelopes, eventos ou entregas já persistidos;
- restaurar banco/arquivos somente em incidente de corrupção confirmado e a
  partir do backup verificado;
- rollback de schema deve ser ensaiado na cópia do PostgreSQL e autorizado
  separadamente, pois pode remover registros criados após a ativação.

## Decisão do gate

O código da R2 está pronto para uma **homologação externa controlada**. A release
não deve ser declarada concluída em produção até que DocuSign/RH e os canais
externos aplicáveis sejam validados. Nenhum deploy foi realizado por este gate.

### STOP R2

Não iniciar R3/EPI automaticamente.
