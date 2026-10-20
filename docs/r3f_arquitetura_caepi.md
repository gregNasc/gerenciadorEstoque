# R3.F — Arquitetura para futura integração CAEPI

A integração foi preparada sem tornar um serviço externo requisito para o
cadastro de EPI.

`integracao.clients.caepi` define o contrato `CaepiProvider` e o resultado
normalizado `CaepiLookupResult`. `CaepiService` recebe o provider por injeção,
normaliza o CA pelo mesmo serviço usado no domínio e rejeita respostas referentes
a outro certificado.

Em 19/10/2026 foi verificado que o MTE oferece a consulta pública individual e
o download da base oficial do CAEPI em CSV, mas não documenta uma API pública
REST/JSON para consulta unitária. Por isso, não foi implementado scraping do
formulário legado.

Na R3.F, o provider padrão era `CaepiDisabledProvider`: retornava `UNAVAILABLE`,
preservava o cadastro manual e apresentava o link oficial do MTE. A R3.G evoluiu
esse contrato para `CaepiDatabaseProvider`, que consulta exclusivamente a última
versão oficial publicada no PostgreSQL pelo Superuser.

Também foi implementado `CaepiHttpProvider`, habilitado somente quando
`CaepiHttpProvider` permanece apenas como adaptador desacoplado e testado para
uma eventual API oficial futura. Ele não é selecionado pelo fluxo operacional
da R3.G e não requer variáveis de ambiente.

Para habilitar a consulta automática na R3.G é necessário:

1. confirmar a fonte e os termos oficiais vigentes;
2. abrir **Base CAEPI** como Superuser, enviar o CSV/ZIP/GZIP oficial e revisar
   a prévia;
3. confirmar a publicação atômica;
4. testar CA encontrado, ausente e catálogo não carregado;
5. manter o cadastro manual como contingência.

Fontes oficiais consultadas:

- `https://caepi.trabalho.gov.br/internet/ConsultaCAInternet.aspx`;
- página de EPI do MTE, que disponibiliza a base oficial em CSV e o dicionário
  de metadados.
