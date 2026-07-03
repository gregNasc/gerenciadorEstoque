# 11 — Infraestrutura

## Objetivo

Este documento define a arquitetura de infraestrutura do Gerenciador de Estoque.

Seu objetivo é documentar o ambiente atual, a estratégia de deploy e a evolução planejada da infraestrutura para suportar o crescimento do sistema.

---

# 1. Filosofia

A infraestrutura deve ser:

* simples;
* segura;
* escalável;
* automatizada;
* facilmente reproduzível.

O ambiente de produção deve refletir o ambiente de desenvolvimento sempre que possível.

---

# 2. Ambientes

O projeto possui três ambientes principais.

```text
Desenvolvimento

↓

Homologação (Futuro)

↓

Produção
```

---

# 3. Desenvolvimento

## Objetivo

Ambiente utilizado durante implementação e testes.

---

## Plataforma

Windows

---

## Linguagem

Python

---

## Framework

Django

---

## Banco

PostgreSQL

---

## IDE

Visual Studio Code

---

## Controle de versão

Git

GitHub

---

# 4. Produção Atual

Atualmente o sistema está hospedado na plataforma Render.

## Serviços utilizados

Aplicação Django

Banco PostgreSQL

Gunicorn

WhiteNoise

---

## Objetivos

Facilidade de deploy.

Baixo custo.

Alta disponibilidade.

---

# 5. Infraestrutura Planejada

A evolução natural da infraestrutura será baseada na AWS.

---

## Arquitetura prevista

```text
Internet

↓

CloudFront

↓

Load Balancer

↓

EC2

↓

Gunicorn

↓

Django

↓

PostgreSQL

↓

Amazon S3
```

---

# 6. Amazon S3

## Objetivo

Centralizar armazenamento de arquivos.

---

## Arquivos previstos

Fotos de equipamentos.

Anexos.

Relatórios.

Exportações.

Arquivos temporários.

Documentos.

---

## Benefícios

Escalabilidade.

Alta disponibilidade.

Baixo custo.

Versionamento.

Integração com CloudFront.

---

# 7. Banco de Dados

## Atual

PostgreSQL.

---

## Estratégia

Backups frequentes.

Índices.

Constraints.

Integridade referencial.

Monitoramento.

---

## Evolução

Possibilidade futura de utilizar Amazon RDS.

---

# 8. Arquivos Estáticos

Atualmente:

WhiteNoise.

Futuramente:

Amazon S3.

CloudFront.

---

# 9. Arquivos de Mídia

Atualmente armazenados junto da aplicação.

Futuramente:

Amazon S3.

---

# 10. Variáveis de Ambiente

Todas as informações sensíveis devem permanecer fora do código.

Exemplos:

```text
SECRET_KEY

DATABASE_URL

DEBUG

EMAIL_HOST

AWS_ACCESS_KEY_ID

AWS_SECRET_ACCESS_KEY

AWS_STORAGE_BUCKET_NAME

WHATSAPP_TOKEN

PLANEJAMENTO_API_KEY
```

Nunca armazenar credenciais no repositório.

---

# 11. Deploy

## Atual

Deploy manual via GitHub → Render.

---

## Futuro

Deploy automatizado.

Pipeline CI/CD.

Validação automática.

Testes automatizados.

---

# 12. Monitoramento

Indicadores desejados.

Tempo de resposta.

Uso de CPU.

Uso de memória.

Banco.

Fila.

Erros.

Logs.

---

# 13. Logs

O sistema deve registrar.

Erros.

Avisos.

Integrações.

Movimentações críticas.

Autenticação.

Exceções.

---

# 14. Backup

Objetivos.

Banco.

Arquivos.

Configurações.

---

## Estratégia

Backup diário.

Retenção.

Teste periódico de restauração.

---

# 15. Segurança

HTTPS obrigatório.

Proteção CSRF.

Proteção XSS.

Proteção SQL Injection.

Validação de permissões.

Controle de autenticação.

Logs de auditoria.

---

# 16. Escalabilidade

A infraestrutura deve permitir crescimento sem necessidade de reescrita da aplicação.

Escalar deve significar apenas adicionar recursos.

---

# 17. Internacionalização

Preparar infraestrutura para múltiplos idiomas.

Português.

Espanhol.

Novos idiomas futuramente.

---

# 18. Disponibilidade

Objetivo de longo prazo.

Alta disponibilidade.

Baixo tempo de indisponibilidade.

Recuperação rápida.

---

# 19. Recuperação de Desastre

Planejamento futuro.

Backup.

Banco.

Arquivos.

Procedimento documentado.

Tempo estimado de recuperação.

---

# 20. Roadmap

## Curto Prazo

Manter Render.

Melhorar monitoramento.

Automatizar backup.

---

## Médio Prazo

Amazon S3.

Separação definitiva de arquivos estáticos e mídia.

Pipeline de deploy.

---

## Longo Prazo

Migração gradual para AWS.

Amazon RDS.

CloudFront.

Balanceamento.

Monitoramento completo.

---

# 21. Diagrama

```text
Desenvolvedor

↓

GitHub

↓

Pipeline

↓

Servidor

↓

Django

↓

Services

↓

PostgreSQL

↓

Amazon S3

↓

Dashboard
```

---

# 22. Filosofia da Infraestrutura

A infraestrutura deve ser transparente para a operação.

O usuário não deve perceber onde o sistema está hospedado.

Ele deve perceber apenas:

* rapidez;
* estabilidade;
* segurança;
* disponibilidade.

---

# Conclusão

A infraestrutura do Gerenciador de Estoque deve evoluir acompanhando o crescimento da plataforma.

O ambiente atual atende plenamente às necessidades da Fase 1 e início da Fase 2.

A migração para AWS será realizada de forma gradual, preservando a disponibilidade do sistema e preparando a plataforma para novos módulos, integrações e crescimento operacional.

Toda evolução deverá priorizar simplicidade, confiabilidade e facilidade de manutenção.
