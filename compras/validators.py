from pathlib import Path
from xml.etree import ElementTree

from django.core.exceptions import ValidationError


LIMITE_DANFE = 20 * 1024 * 1024
LIMITE_XML_NFE = 10 * 1024 * 1024


def _conteudo(arquivo):
    estava_fechado = bool(getattr(arquivo, 'closed', False))
    posicao = arquivo.tell() if hasattr(arquivo, 'tell') else 0
    try:
        return arquivo.read()
    finally:
        if hasattr(arquivo, 'seek'):
            arquivo.seek(posicao)
        if estava_fechado and hasattr(arquivo, 'close'):
            arquivo.close()


def _validar_tamanho(arquivo, limite, descricao):
    if arquivo.size <= 0:
        raise ValidationError(f'O arquivo {descricao} está vazio.')
    if arquivo.size > limite:
        tamanho_mb = limite // (1024 * 1024)
        raise ValidationError(
            f'O arquivo {descricao} deve ter no máximo {tamanho_mb} MB.'
        )


def validar_danfe_pdf(arquivo):
    _validar_tamanho(arquivo, LIMITE_DANFE, 'DANFE')
    if Path(arquivo.name).suffix.lower() != '.pdf':
        raise ValidationError('Envie o DANFE em formato PDF.')
    estava_fechado = bool(getattr(arquivo, 'closed', False))
    posicao = arquivo.tell() if hasattr(arquivo, 'tell') else 0
    try:
        assinatura = arquivo.read(5)
    finally:
        if hasattr(arquivo, 'seek'):
            arquivo.seek(posicao)
        if estava_fechado and hasattr(arquivo, 'close'):
            arquivo.close()
    if assinatura != b'%PDF-':
        raise ValidationError('O conteúdo enviado não corresponde a um PDF válido.')


def validar_xml_nfe(arquivo):
    _validar_tamanho(arquivo, LIMITE_XML_NFE, 'XML da NF-e')
    if Path(arquivo.name).suffix.lower() != '.xml':
        raise ValidationError('Envie a NF-e em formato XML.')
    conteudo = _conteudo(arquivo)
    conteudo_maiusculo = conteudo[:65536].upper()
    if b'<!DOCTYPE' in conteudo_maiusculo or b'<!ENTITY' in conteudo_maiusculo:
        raise ValidationError('O XML contém declarações não permitidas.')
    try:
        raiz = ElementTree.fromstring(conteudo)
    except (ElementTree.ParseError, ValueError, UnicodeError) as exc:
        raise ValidationError('O arquivo XML da NF-e não está bem formado.') from exc
    nome_raiz = raiz.tag.rsplit('}', 1)[-1]
    if nome_raiz not in {'NFe', 'nfeProc'}:
        raise ValidationError(
            'O XML enviado não corresponde a uma NF-e ou processo de NF-e.'
        )
