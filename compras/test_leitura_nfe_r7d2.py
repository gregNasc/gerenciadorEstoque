from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from compras.eventos import EventoCompraTipo
from compras.models import (
    Aquisicao,
    CodigoCatalogo,
    EventoCompra,
    FornecedorEmpresa,
    ItemAquisicao,
    NotaFiscalAquisicao,
)
from compras.services import AquisicaoService
from estoque.models import Base, Empresa, Perfil, Produto
from insumos.models import CategoriaInsumo, FornecedorInsumo, Insumo


class LeituraNFeR7D2Tests(TestCase):
    CHAVE = '35261032000000000101550010000001231123456789'

    def setUp(self):
        self.diretorios = TemporaryDirectory(
            dir=settings.BASE_DIR,
            prefix='_test_leitura_nfe_',
        )
        raiz = Path(self.diretorios.name)
        self.override = override_settings(STORAGES={
            'default': {
                'BACKEND': 'django.core.files.storage.FileSystemStorage',
                'OPTIONS': {'location': raiz / 'publico', 'base_url': '/media/'},
            },
            'private': {
                'BACKEND': 'django.core.files.storage.FileSystemStorage',
                'OPTIONS': {'location': raiz / 'privado', 'base_url': None},
            },
            'staticfiles': {
                'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
            },
        })
        self.override.enable()
        self.empresa = Empresa.objects.create(nome='Empresa Leitura NF-e')
        self.outra_empresa = Empresa.objects.create(nome='Outra Empresa NF-e')
        self.base = Base.objects.create(nome='BASE NF-E', empresa=self.empresa)
        self.admin = self._usuario('admin.leitura.nfe', self.empresa, Perfil.Role.ADMIN)
        self.gestor = self._usuario(
            'gestor.leitura.nfe', self.empresa, Perfil.Role.GESTOR, self.base,
        )
        self.jose = self._usuario('jose.barboza', self.empresa, Perfil.Role.ADMIN)
        self.outro_admin = self._usuario(
            'admin.outra.nfe', self.outra_empresa, Perfil.Role.ADMIN,
        )
        self.fornecedor = FornecedorInsumo.objects.create(
            nome='Fornecedor XML Ltda', documento='32000000000101',
        )
        FornecedorEmpresa.objects.create(
            empresa=self.empresa,
            fornecedor=self.fornecedor,
            status=FornecedorEmpresa.Status.HOMOLOGADO,
            cadastrado_por=self.admin,
            homologado_por=self.admin,
        )
        categoria = CategoriaInsumo.objects.create(nome='Categoria XML')
        self.insumo = Insumo.objects.create(
            descricao='Item já solicitado', categoria=categoria, unidade_medida='UN',
        )

    def tearDown(self):
        self.override.disable()
        self.diretorios.cleanup()

    @staticmethod
    def _usuario(username, empresa, role, base=None):
        usuario = User.objects.create_user(username, password='Teste123!')
        usuario.perfil.empresa = empresa
        usuario.perfil.role = role
        usuario.perfil.save()
        if base is not None:
            usuario.perfil.regionais.add(base)
        return usuario

    @classmethod
    def _xml(cls, *, cnpj='32000000000101'):
        conteudo = f'''<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
  <NFe><infNFe Id="NFe{cls.CHAVE}">
    <ide><serie>7</serie><nNF>4567</nNF><dhEmi>2026-10-29T09:30:00-03:00</dhEmi></ide>
    <emit><CNPJ>{cnpj}</CNPJ><xNome>Fornecedor XML Ltda</xNome></emit>
    <det nItem="1"><prod><cProd>FORN-001</cProd><cEAN>7891234567890</cEAN>
      <xProd>Produto ainda não catalogado</xProd><NCM>84713012</NCM><CFOP>5102</CFOP>
      <uCom>UN</uCom><qCom>3.0000</qCom><vUnCom>125.500000</vUnCom><vProd>376.50</vProd>
    </prod></det>
    <total><ICMSTot><vProd>376.50</vProd><vFrete>20.00</vFrete><vDesc>5.00</vDesc>
      <vICMS>45.18</vICMS><vST>0</vST><vIPI>0</vIPI><vII>0</vII>
      <vPIS>6.21</vPIS><vCOFINS>28.60</vCOFINS><vNF>391.50</vNF>
    </ICMSTot></total>
  </infNFe></NFe>
</nfeProc>'''.encode()
        return SimpleUploadedFile('nota.xml', conteudo, content_type='application/xml')

    def _criar(self, **dados):
        return AquisicaoService.criar(
            empresa=self.empresa,
            fornecedor=self.fornecedor,
            usuario=self.admin,
            arquivo_xml_nfe=dados.pop('arquivo_xml_nfe', self._xml()),
            itens=[{
                'tipo_item': ItemAquisicao.Tipo.INSUMO,
                'insumo': self.insumo,
                'quantidade': Decimal('3'),
                'valor_unitario': Decimal('125.50'),
            }],
            **dados,
        )

    def test_upload_processa_snapshot_completo_sem_criar_catalogo(self):
        produtos_antes = Produto.objects.count()
        codigos_antes = CodigoCatalogo.objects.count()

        aquisicao = self._criar()
        aquisicao.refresh_from_db()
        nota = aquisicao.nota_fiscal
        item = nota.itens.get()

        self.assertEqual(aquisicao.chave_nfe, self.CHAVE)
        self.assertEqual(aquisicao.numero_documento, '4567')
        self.assertEqual(nota.situacao, NotaFiscalAquisicao.Situacao.PROCESSADA)
        self.assertEqual(nota.serie, '7')
        self.assertEqual(nota.emitente_cnpj, '32000000000101')
        self.assertEqual(nota.valor_nota, Decimal('391.50'))
        self.assertEqual(nota.valor_impostos, Decimal('79.99'))
        self.assertEqual(item.codigo_fornecedor, 'FORN-001')
        self.assertEqual(item.ean_gtin, '7891234567890')
        self.assertEqual(item.ncm, '84713012')
        self.assertEqual(item.cfop, '5102')
        self.assertEqual(item.quantidade, Decimal('3.0000'))
        self.assertEqual(Produto.objects.count(), produtos_antes)
        self.assertEqual(CodigoCatalogo.objects.count(), codigos_antes)

    def test_divergencias_sao_exibidas_sem_sobrescrever_dados_informados(self):
        aquisicao = self._criar(
            numero_documento='MANUAL-9',
            chave_nfe='9' * 44,
        )
        aquisicao.refresh_from_db()

        self.assertEqual(aquisicao.numero_documento, 'MANUAL-9')
        self.assertEqual(aquisicao.chave_nfe, '9' * 44)
        self.assertEqual(
            aquisicao.nota_fiscal.situacao,
            NotaFiscalAquisicao.Situacao.DIVERGENTE,
        )
        self.assertEqual(len(aquisicao.nota_fiscal.divergencias), 2)

    def test_reprocessamento_e_idempotente_e_bloqueia_perfis_sem_preco(self):
        aquisicao = self._criar()
        url = reverse('compras:aquisicao_processar_xml', args=[aquisicao.pk])
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(NotaFiscalAquisicao.objects.count(), 1)
        self.assertEqual(
            EventoCompra.objects.filter(tipo=EventoCompraTipo.NFE_PROCESSADA).count(),
            1,
        )

        for usuario in (self.gestor, self.jose, self.outro_admin):
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                self.assertEqual(self.client.post(url).status_code, 404)

    def test_xml_sem_estrutura_fiscal_nao_cria_aquisicao_nem_arquivo(self):
        invalido = SimpleUploadedFile(
            'nota.xml',
            b'<nfeProc><NFe></NFe></nfeProc>',
            content_type='application/xml',
        )
        with self.assertRaisesMessage(
            ValidationError,
            'O XML não contém a estrutura infNFe esperada.',
        ):
            self._criar(arquivo_xml_nfe=invalido)
        self.assertFalse(Aquisicao.objects.exists())
