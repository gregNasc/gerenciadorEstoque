import hashlib
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from compras.eventos import EventoCompraTipo
from compras.models import (
    Aquisicao,
    CatalogoProdutoEmpresa,
    CodigoCatalogo,
    EventoCompra,
    ItemNotaFiscalAquisicao,
    NotaFiscalAquisicao,
)
from compras.policies import AquisicaoAccessPolicy


def _nome_local(elemento):
    return elemento.tag.rsplit('}', 1)[-1]


def _filho(elemento, nome):
    if elemento is None:
        return None
    return next((filho for filho in elemento if _nome_local(filho) == nome), None)


def _descendente(elemento, nome):
    if elemento is None:
        return None
    return next((item for item in elemento.iter() if _nome_local(item) == nome), None)


def _texto(elemento, nome, padrao=''):
    filho = _filho(elemento, nome)
    return (filho.text or '').strip() if filho is not None else padrao


def _decimal(valor, campo):
    valor = str(valor or '0').strip().replace(',', '.')
    try:
        numero = Decimal(valor)
    except InvalidOperation as exc:
        raise ValidationError(f'O campo {campo} da NF-e possui valor inválido.') from exc
    if numero < 0:
        raise ValidationError(f'O campo {campo} da NF-e não pode ser negativo.')
    return numero


def _data_emissao(valor):
    if not valor:
        return None
    data_hora = parse_datetime(valor)
    if data_hora is not None:
        if timezone.is_naive(data_hora):
            data_hora = timezone.make_aware(data_hora)
        return data_hora
    data = parse_date(valor)
    if data is not None:
        return timezone.make_aware(datetime.combine(data, time.min))
    raise ValidationError('A data de emissão da NF-e é inválida.')


@dataclass(frozen=True)
class ItemNFeLido:
    numero_item: int
    codigo_fornecedor: str
    ean_gtin: str
    descricao: str
    ncm: str
    cfop: str
    unidade: str
    quantidade: Decimal
    valor_unitario: Decimal
    valor_total: Decimal


@dataclass(frozen=True)
class NFeLida:
    chave_acesso: str
    numero: str
    serie: str
    data_emissao: datetime | None
    emitente_cnpj: str
    emitente_nome: str
    valor_produtos: Decimal
    valor_frete: Decimal
    valor_desconto: Decimal
    valor_impostos: Decimal
    valor_nota: Decimal
    itens: tuple[ItemNFeLido, ...]
    hash_xml: str


class LeitorNFe:
    @classmethod
    def ler(cls, conteudo):
        if b'<!DOCTYPE' in conteudo.upper() or b'<!ENTITY' in conteudo.upper():
            raise ValidationError('O XML contém declarações externas não permitidas.')
        try:
            raiz = ElementTree.fromstring(conteudo)
        except ElementTree.ParseError as exc:
            raise ValidationError('O arquivo XML da NF-e não está bem formado.') from exc
        inf_nfe = _descendente(raiz, 'infNFe')
        if inf_nfe is None:
            raise ValidationError('O XML não contém a estrutura infNFe esperada.')

        identificacao = _filho(inf_nfe, 'ide')
        emitente = _filho(inf_nfe, 'emit')
        total = _descendente(_filho(inf_nfe, 'total'), 'ICMSTot')
        chave = (inf_nfe.attrib.get('Id') or '').removeprefix('NFe').strip()
        if len(chave) != 44 or not chave.isdigit():
            raise ValidationError('A chave de acesso extraída da NF-e é inválida.')
        numero = _texto(identificacao, 'nNF')
        if not numero:
            raise ValidationError('O número da NF-e não foi encontrado no XML.')

        itens = []
        for posicao, detalhe in enumerate(
            (item for item in inf_nfe if _nome_local(item) == 'det'),
            start=1,
        ):
            produto = _filho(detalhe, 'prod')
            descricao = _texto(produto, 'xProd')
            if not descricao:
                raise ValidationError(f'O item {posicao} da NF-e não possui descrição.')
            numero_item = detalhe.attrib.get('nItem', str(posicao))
            if not str(numero_item).isdigit():
                numero_item = posicao
            ean = _texto(produto, 'cEANTrib') or _texto(produto, 'cEAN')
            if ean.upper() == 'SEM GTIN':
                ean = ''
            itens.append(ItemNFeLido(
                numero_item=int(numero_item),
                codigo_fornecedor=_texto(produto, 'cProd')[:100],
                ean_gtin=ean[:30],
                descricao=descricao[:500],
                ncm=_texto(produto, 'NCM')[:12],
                cfop=_texto(produto, 'CFOP')[:10],
                unidade=(_texto(produto, 'uCom') or _texto(produto, 'uTrib'))[:20],
                quantidade=_decimal(
                    _texto(produto, 'qCom') or _texto(produto, 'qTrib'),
                    f'quantidade do item {posicao}',
                ),
                valor_unitario=_decimal(
                    _texto(produto, 'vUnCom') or _texto(produto, 'vUnTrib'),
                    f'valor unitário do item {posicao}',
                ),
                valor_total=_decimal(
                    _texto(produto, 'vProd'),
                    f'valor total do item {posicao}',
                ),
            ))
        if not itens:
            raise ValidationError('A NF-e não possui itens de produto.')

        impostos = sum((
            _decimal(_texto(total, campo), campo)
            for campo in ('vICMS', 'vST', 'vIPI', 'vII', 'vPIS', 'vCOFINS')
        ), Decimal('0'))
        return NFeLida(
            chave_acesso=chave,
            numero=numero[:30],
            serie=_texto(identificacao, 'serie')[:10],
            data_emissao=_data_emissao(
                _texto(identificacao, 'dhEmi') or _texto(identificacao, 'dEmi')
            ),
            emitente_cnpj=''.join(
                caractere for caractere in _texto(emitente, 'CNPJ') if caractere.isdigit()
            )[:14],
            emitente_nome=_texto(emitente, 'xNome')[:255],
            valor_produtos=_decimal(_texto(total, 'vProd'), 'valor dos produtos'),
            valor_frete=_decimal(_texto(total, 'vFrete'), 'frete'),
            valor_desconto=_decimal(_texto(total, 'vDesc'), 'desconto'),
            valor_impostos=impostos,
            valor_nota=_decimal(_texto(total, 'vNF'), 'valor da nota'),
            itens=tuple(itens),
            hash_xml=hashlib.sha256(conteudo).hexdigest(),
        )


class NFeAquisicaoService:
    @staticmethod
    def _conteudo_xml(aquisicao):
        arquivo = aquisicao.arquivo_xml_nfe
        if not arquivo:
            raise ValidationError('Anexe o XML da NF-e antes de processá-lo.')
        estava_fechado = getattr(arquivo, 'closed', True)
        try:
            arquivo.open('rb')
            conteudo = arquivo.read()
            arquivo.seek(0)
            return conteudo
        finally:
            if estava_fechado:
                arquivo.close()

    @classmethod
    @transaction.atomic
    def processar(cls, *, aquisicao, usuario):
        if not AquisicaoAccessPolicy.documentos(usuario).filter(pk=aquisicao.pk).exists():
            raise PermissionDenied('Sem permissão para processar documentos fiscais.')
        aquisicao = Aquisicao.objects.select_for_update().select_related(
            'fornecedor', 'empresa',
        ).get(pk=aquisicao.pk)
        dados = LeitorNFe.ler(cls._conteudo_xml(aquisicao))

        repetida = Aquisicao.objects.filter(
            empresa=aquisicao.empresa,
            chave_nfe=dados.chave_acesso,
        ).exclude(pk=aquisicao.pk).exists()
        if repetida:
            raise ValidationError('Esta chave de NF-e já pertence a outra aquisição da empresa.')

        divergencias = []
        if aquisicao.chave_nfe and aquisicao.chave_nfe != dados.chave_acesso:
            divergencias.append('A chave informada na aquisição difere do XML.')
        if aquisicao.numero_documento and aquisicao.numero_documento != dados.numero:
            divergencias.append('O número do documento informado difere do XML.')
        documento_fornecedor = ''.join(
            caractere for caractere in (aquisicao.fornecedor.documento or '')
            if caractere.isdigit()
        )
        if documento_fornecedor and dados.emitente_cnpj != documento_fornecedor:
            divergencias.append('O CNPJ do emitente difere do fornecedor selecionado.')

        nota_anterior = NotaFiscalAquisicao.objects.filter(aquisicao=aquisicao).first()
        alterado = nota_anterior is None or nota_anterior.hash_xml != dados.hash_xml
        nota, _ = NotaFiscalAquisicao.objects.update_or_create(
            aquisicao=aquisicao,
            defaults={
                'chave_acesso': dados.chave_acesso,
                'numero': dados.numero,
                'serie': dados.serie,
                'data_emissao': dados.data_emissao,
                'emitente_cnpj': dados.emitente_cnpj,
                'emitente_nome': dados.emitente_nome,
                'valor_produtos': dados.valor_produtos,
                'valor_frete': dados.valor_frete,
                'valor_desconto': dados.valor_desconto,
                'valor_impostos': dados.valor_impostos,
                'valor_nota': dados.valor_nota,
                'situacao': (
                    NotaFiscalAquisicao.Situacao.DIVERGENTE
                    if divergencias else NotaFiscalAquisicao.Situacao.PROCESSADA
                ),
                'divergencias': divergencias,
                'hash_xml': dados.hash_xml,
                'processado_por': usuario,
            },
        )
        if alterado:
            nota.itens.all().delete()
            ItemNotaFiscalAquisicao.objects.bulk_create([
                ItemNotaFiscalAquisicao(nota_fiscal=nota, **item.__dict__)
                for item in dados.itens
            ])

        campos_atualizados = []
        if not aquisicao.chave_nfe:
            aquisicao.chave_nfe = dados.chave_acesso
            campos_atualizados.append('chave_nfe')
        if not aquisicao.numero_documento:
            aquisicao.numero_documento = dados.numero
            campos_atualizados.append('numero_documento')
        if campos_atualizados:
            aquisicao.save(update_fields=[*campos_atualizados, 'atualizado_em'])

        if alterado:
            EventoCompra.objects.create(
                aquisicao=aquisicao,
                tipo=EventoCompraTipo.NFE_PROCESSADA,
                usuario=usuario,
                dados={
                    'nota_fiscal_id': nota.pk,
                    'hash_xml': dados.hash_xml,
                    'itens': len(dados.itens),
                    'divergencias': len(divergencias),
                },
            )
        CatalogoNFeService.analisar(nota=nota, usuario=usuario)
        return nota, alterado


class CatalogoNFeService:
    @staticmethod
    def _chave_referencia(*, produto_id=None, insumo_id=None):
        if produto_id:
            return ('PRODUTO', produto_id)
        if insumo_id:
            return ('INSUMO', insumo_id)
        return None

    @staticmethod
    def _insumos_da_empresa(empresa_id):
        from insumos.models import SaldoInsumoBase

        ids = set(SaldoInsumoBase.objects.filter(
            base__empresa_id=empresa_id,
            insumo__ativo=True,
        ).values_list('insumo_id', flat=True))
        ids.update(CodigoCatalogo.objects.filter(
            empresa_id=empresa_id,
            insumo__ativo=True,
            ativo=True,
        ).values_list('insumo_id', flat=True))
        return ids

    @classmethod
    def _sugestao(cls, item):
        empresa_id = item.nota_fiscal.aquisicao.empresa_id
        filtros = []
        if item.ean_gtin:
            filtros.append((CodigoCatalogo.Tipo.EAN_GTIN, item.ean_gtin, 'EAN/GTIN'))
        if item.codigo_fornecedor:
            filtros.extend([
                (
                    CodigoCatalogo.Tipo.CODIGO_FORNECEDOR,
                    item.codigo_fornecedor,
                    'código do fornecedor',
                ),
                (
                    CodigoCatalogo.Tipo.SKU_FABRICANTE,
                    item.codigo_fornecedor,
                    'SKU do fabricante',
                ),
            ])

        encontrados = {}
        for tipo, codigo, criterio in filtros:
            for registro in CodigoCatalogo.objects.filter(
                empresa_id=empresa_id,
                tipo=tipo,
                codigo=codigo,
                ativo=True,
            ).select_related('produto', 'insumo'):
                chave = cls._chave_referencia(
                    produto_id=registro.produto_id,
                    insumo_id=registro.insumo_id,
                )
                if chave:
                    encontrados[chave] = (registro, criterio)
        if len(encontrados) == 1:
            registro, criterio = next(iter(encontrados.values()))
            return registro.produto, registro.insumo, registro, criterio
        if len(encontrados) > 1:
            return None, None, None, 'Códigos apontam para itens diferentes'

        produtos = list(CatalogoProdutoEmpresa.objects.filter(
            empresa_id=empresa_id,
            ativo=True,
            produto__ativo=True,
            produto__descricao__iexact=item.descricao,
        ).select_related('produto')[:2])
        from insumos.models import Insumo
        insumos = list(Insumo.objects.filter(
            pk__in=cls._insumos_da_empresa(empresa_id),
            ativo=True,
            descricao__iexact=item.descricao,
        )[:2])
        candidatos = [
            (catalogo.produto, None) for catalogo in produtos
        ] + [(None, insumo) for insumo in insumos]
        if len(candidatos) == 1:
            produto, insumo = candidatos[0]
            return produto, insumo, None, 'descrição exata'
        if len(candidatos) > 1:
            return None, None, None, 'Descrição corresponde a mais de um item'
        return None, None, None, ''

    @classmethod
    @transaction.atomic
    def analisar(cls, *, nota, usuario):
        if not AquisicaoAccessPolicy.documentos(usuario).filter(
            pk=nota.aquisicao_id,
        ).exists():
            raise PermissionDenied('Sem permissão para analisar o catálogo da NF-e.')
        itens = ItemNotaFiscalAquisicao.objects.select_for_update().filter(
            nota_fiscal=nota,
        ).select_related('nota_fiscal__aquisicao')
        for item in itens:
            if item.status_catalogo == ItemNotaFiscalAquisicao.StatusCatalogo.CONFIRMADO:
                continue
            produto, insumo, codigo, criterio = cls._sugestao(item)
            item.produto_catalogo = produto
            item.insumo_catalogo = insumo
            item.codigo_catalogo = codigo
            item.criterio_catalogo = criterio
            item.status_catalogo = (
                ItemNotaFiscalAquisicao.StatusCatalogo.SUGERIDO
                if produto or insumo
                else ItemNotaFiscalAquisicao.StatusCatalogo.NAO_ENCONTRADO
            )
            item.resolvido_por = None
            item.resolvido_em = None
            item.save(update_fields=[
                'produto_catalogo', 'insumo_catalogo', 'codigo_catalogo',
                'criterio_catalogo', 'status_catalogo', 'resolvido_por',
                'resolvido_em',
            ])
        return nota

    @classmethod
    def _registrar_codigo(cls, *, item, tipo, codigo, usuario):
        if not codigo:
            return None
        empresa = item.nota_fiscal.aquisicao.empresa
        existente = CodigoCatalogo.objects.filter(
            empresa=empresa,
            tipo=tipo,
            codigo=codigo,
        ).first()
        referencia = cls._chave_referencia(
            produto_id=item.produto_catalogo_id,
            insumo_id=item.insumo_catalogo_id,
        )
        if existente:
            referencia_existente = cls._chave_referencia(
                produto_id=existente.produto_id,
                insumo_id=existente.insumo_id,
            )
            if referencia_existente != referencia:
                raise ValidationError(
                    f'O {existente.get_tipo_display()} já identifica outro item.'
                )
            if not existente.ativo:
                existente.ativo = True
                existente.save(update_fields=['ativo', 'atualizado_em'])
            return existente
        return CodigoCatalogo.objects.create(
            empresa=empresa,
            produto=item.produto_catalogo,
            insumo=item.insumo_catalogo,
            tipo=tipo,
            codigo=codigo,
            criado_por=usuario,
        )

    @classmethod
    @transaction.atomic
    def confirmar(cls, *, item, usuario):
        item = ItemNotaFiscalAquisicao.objects.select_for_update().select_related(
            'nota_fiscal__aquisicao__empresa', 'produto_catalogo', 'insumo_catalogo',
        ).get(pk=item.pk)
        aquisicao = item.nota_fiscal.aquisicao
        if not AquisicaoAccessPolicy.documentos(usuario).filter(pk=aquisicao.pk).exists():
            raise PermissionDenied('Sem permissão para confirmar o catálogo da NF-e.')
        if item.status_catalogo == ItemNotaFiscalAquisicao.StatusCatalogo.CONFIRMADO:
            return item, False
        if (
            item.status_catalogo != ItemNotaFiscalAquisicao.StatusCatalogo.SUGERIDO
            or not (item.produto_catalogo_id or item.insumo_catalogo_id)
        ):
            raise ValidationError('Este item ainda não possui uma correspondência para confirmar.')

        principal = cls._registrar_codigo(
            item=item,
            tipo=CodigoCatalogo.Tipo.EAN_GTIN,
            codigo=item.ean_gtin,
            usuario=usuario,
        )
        codigo_fornecedor = cls._registrar_codigo(
            item=item,
            tipo=CodigoCatalogo.Tipo.CODIGO_FORNECEDOR,
            codigo=item.codigo_fornecedor,
            usuario=usuario,
        )
        item.codigo_catalogo = principal or codigo_fornecedor or item.codigo_catalogo
        item.status_catalogo = ItemNotaFiscalAquisicao.StatusCatalogo.CONFIRMADO
        item.resolvido_por = usuario
        item.resolvido_em = timezone.now()
        item.save(update_fields=[
            'codigo_catalogo', 'status_catalogo', 'resolvido_por', 'resolvido_em',
        ])
        EventoCompra.objects.create(
            aquisicao=aquisicao,
            tipo=EventoCompraTipo.NFE_ITEM_CATALOGO_CONFIRMADO,
            usuario=usuario,
            dados={
                'nota_fiscal_id': item.nota_fiscal_id,
                'item_nfe_id': item.pk,
                'tipo_item': 'EQUIPAMENTO' if item.produto_catalogo_id else 'INSUMO',
                'item_catalogo_id': item.produto_catalogo_id or item.insumo_catalogo_id,
            },
        )
        return item, True

    @classmethod
    @transaction.atomic
    def confirmar_cadastro_assistido(
        cls,
        *,
        item,
        usuario,
        produto=None,
        insumo=None,
        empresa,
    ):
        item = ItemNotaFiscalAquisicao.objects.select_for_update().select_related(
            'nota_fiscal__aquisicao',
        ).get(pk=item.pk)
        aquisicao = item.nota_fiscal.aquisicao
        if not AquisicaoAccessPolicy.documentos(usuario).filter(pk=aquisicao.pk).exists():
            raise PermissionDenied('Sem permissão para vincular o cadastro à NF-e.')
        if aquisicao.empresa_id != empresa.pk:
            raise PermissionDenied('O novo item deve pertencer à empresa da NF-e.')
        if item.status_catalogo != ItemNotaFiscalAquisicao.StatusCatalogo.NAO_ENCONTRADO:
            raise ValidationError(
                'O cadastro assistido só pode ser usado para item não encontrado.'
            )
        if bool(produto) == bool(insumo):
            raise ValidationError('Informe somente um equipamento ou um insumo.')
        if produto and not CatalogoProdutoEmpresa.objects.filter(
            empresa=empresa,
            produto=produto,
            ativo=True,
        ).exists():
            raise ValidationError('O equipamento não está ativo no catálogo da empresa.')
        if insumo and insumo.pk not in cls._insumos_da_empresa(empresa.pk):
            raise ValidationError('O insumo ainda não está vinculado à empresa da NF-e.')

        item.produto_catalogo = produto
        item.insumo_catalogo = insumo
        item.codigo_catalogo = None
        item.criterio_catalogo = 'CADASTRO ASSISTIDO A PARTIR DA NF-E'
        item.status_catalogo = ItemNotaFiscalAquisicao.StatusCatalogo.SUGERIDO
        item.resolvido_por = None
        item.resolvido_em = None
        item.save(update_fields=[
            'produto_catalogo', 'insumo_catalogo', 'codigo_catalogo',
            'criterio_catalogo', 'status_catalogo', 'resolvido_por',
            'resolvido_em',
        ])
        return cls.confirmar(item=item, usuario=usuario)
