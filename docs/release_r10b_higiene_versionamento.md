# R10.B — Higiene de versionamento e artefatos estáticos

**Data:** 10/11/2026  
**Status:** PATCH REVERSÍVEL CONCLUÍDO; VALIDAÇÃO DE `collectstatic` PENDENTE  
**Alterações de dados ou schema:** nenhuma  

## Escopo executado

- `.idea/` e `.test-tmp-*/` foram adicionados ao `.gitignore`;
- os sete arquivos de configuração do IDE saíram somente do índice Git;
- a pasta `.idea/` e seus arquivos locais foram preservados;
- o ZIP estático `white-gradient-background-modern-design.zip` foi auditado e
  retirado do projeto.

## Evidência do ZIP removido

| Verificação | Resultado |
| --- | --- |
| Tamanho | 8.555.348 bytes |
| SHA-256 do ZIP | `B754B71E721E059D9C87EC3CDB359E2DEC6E94C41F80DA756AFFECBE320EFDAC` |
| Histórico | adicionado no commit inicial `1392153`; nenhuma alteração posterior |
| Referências no runtime | nenhuma referência em templates, CSS, JavaScript ou código |
| Conteúdo | `konsis 7.eps` e `konsis 7.jpg` |
| JPG interno | idêntico ao arquivo ativo `estoque/static/images/estoque.jpg` |
| SHA-256 dos JPGs | `510B883208B4BAA7E66446C9247986D338234C3206295A615DF9C2CFC00D2AF9` |

O fundo ativo continua sendo carregado pelo `style.css` a partir de
`images/estoque.jpg`. A remoção do ZIP não removeu nem alterou essa imagem.

## Recuperação

As exclusões são recuperáveis pelo Git. O ZIP permanece disponível no commit
anterior e pode ser restaurado com:

```powershell
git restore --source=HEAD^ -- estoque/static/images/white-gradient-background-modern-design.zip
```

Os arquivos `.idea` continuam fisicamente no checkout local; apenas deixaram de
ser versionados.

## Validação

- `python manage.py check`: aprovado, sem problemas;
- `git diff --check`: aprovado;
- regras do `.gitignore`: confirmadas por `git check-ignore`;
- busca de referências do ZIP: somente o relatório histórico R10.A;
- `collectstatic --dry-run`: iniciado mais de uma vez, mas não retornou no
  ambiente local e precisou ser interrompido sem modificar arquivos;
- testes de login/dashboard: não executados neste patch porque a inicialização
  dos comandos Django que dependem do ambiente de teste apresentou a mesma
  espera sem retorno.

O patch não deve ser apresentado como gate integralmente aprovado até que
`collectstatic` e os testes dirigidos sejam executados em um ambiente em que os
comandos concluam normalmente, como o pipeline de build ou a homologação.

## Limite da subetapa

Nenhum template, dependência, migration, model ou arquivo de mídia operacional
foi removido. A próxima limpeza só deve começar depois da apresentação e
aceitação deste resultado.
