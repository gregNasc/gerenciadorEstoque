from dataclasses import dataclass
from types import MappingProxyType
from urllib.parse import urljoin, urlparse

from django.conf import settings


class TemplatePayloadError(ValueError):
    pass


@dataclass(frozen=True)
class TemplateWhatsApp:
    codigo: str
    nome_meta: str
    campos_corpo: tuple[str, ...]
    idioma_padrao: str = 'pt_BR'
    botao_url: bool = True


def _template(codigo, *, campos=('titulo', 'mensagem'), botao_url=True):
    return TemplateWhatsApp(
        codigo=codigo,
        nome_meta=codigo,
        campos_corpo=tuple(campos),
        botao_url=botao_url,
    )


# Registro deliberadamente imutável. Cada código representa um template que
# precisa existir e ser aprovado com a mesma estrutura na Meta.
REGISTRO_TEMPLATES = MappingProxyType({
    codigo: _template(codigo)
    for codigo in (
        'auditoria_aberta',
        'auditoria_proxima_vencimento',
        'auditoria_enviada',
        'auditoria_resultado_final',
        'auditoria_correcao_solicitada',
        'auditoria_divergencia',
        'auditoria_equipamento_mantido',
        'auditoria_transferencia_criada',
        'auditoria_campanha_acao',
        'transferencia_enviada',
        'transferencia_recebida',
        'emprestimo_enviado',
        'emprestimo_recebido',
        'comunicado_urgente',
        'chamado_acao',
    )
})

MAPA_IDIOMAS = MappingProxyType({
    'pt-br': 'pt_BR',
    'pt_BR': 'pt_BR',
    'es': 'es',
    'en': 'en_US',
    'en-us': 'en_US',
    'en_US': 'en_US',
})


def codigo_template(comunicado):
    dados = comunicado.dados or {}
    codigo = dados.get('template_codigo')
    if codigo:
        return codigo if codigo in REGISTRO_TEMPLATES else None
    if comunicado.tipo == 'URGENTE':
        return 'comunicado_urgente'
    return None


def idioma_meta(idioma, padrao='pt_BR'):
    if not idioma:
        return padrao
    try:
        return MAPA_IDIOMAS[idioma]
    except KeyError as exc:
        raise TemplatePayloadError('IDIOMA NÃO SUPORTADO PARA WHATSAPP.') from exc


def construir_url_absoluta(caminho):
    base = (settings.APP_BASE_URL or '').strip().rstrip('/') + '/'
    if not base:
        raise TemplatePayloadError('APP_BASE_URL NÃO CONFIGURADA.')
    if not settings.DEBUG and urlparse(base).scheme != 'https':
        raise TemplatePayloadError('APP_BASE_URL DEVE USAR HTTPS EM PRODUÇÃO.')
    caminho = (caminho or '/').strip()
    absoluta = urljoin(base, caminho.lstrip('/'))
    if urlparse(absoluta).scheme not in {'http', 'https'}:
        raise TemplatePayloadError('URL DO COMUNICADO É INVÁLIDA.')
    return absoluta


def construir_payload(*, template_codigo, idioma, parametros):
    template = REGISTRO_TEMPLATES.get(template_codigo)
    if template is None:
        raise TemplatePayloadError('TEMPLATE DE WHATSAPP NÃO CADASTRADO.')
    if not isinstance(parametros, dict):
        raise TemplatePayloadError('PARÂMETROS DO TEMPLATE SÃO INVÁLIDOS.')

    corpo = []
    for campo in template.campos_corpo:
        valor = parametros.get(campo)
        # A posição é preservada; templates Meta são posicionais.
        corpo.append({'type': 'text', 'text': str(valor).strip() if valor not in (None, '') else '-'})
    if len(corpo) != len(template.campos_corpo):
        raise TemplatePayloadError('QUANTIDADE DE PARÂMETROS DO TEMPLATE É INVÁLIDA.')

    componentes = [{'type': 'body', 'parameters': corpo}]
    if template.botao_url:
        componentes.append({
            'type': 'button',
            'sub_type': 'url',
            'index': '0',
            'parameters': [{
                'type': 'text',
                'text': construir_url_absoluta(parametros.get('url')),
            }],
        })

    return {
        'messaging_product': 'whatsapp',
        'type': 'template',
        'template': {
            'name': template.nome_meta,
            'language': {'code': idioma_meta(idioma, template.idioma_padrao)},
            'components': componentes,
        },
    }
