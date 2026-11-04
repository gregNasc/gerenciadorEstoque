from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from compras.models import Aquisicao, FornecedorEmpresa, ItemAquisicao
from compras.services import AquisicaoService
from estoque.models import Base, Empresa, Perfil
from insumos.models import CategoriaInsumo, FornecedorInsumo, Insumo


class DocumentosNFeR7DTests(TestCase):
    def setUp(self):
        self.diretorios = TemporaryDirectory(
            dir=settings.BASE_DIR,
            prefix='_test_documentos_nfe_',
        )
        raiz = Path(self.diretorios.name)
        self.publico = raiz / 'publico'
        self.privado = raiz / 'privado'
        self.override = override_settings(STORAGES={
            'default': {
                'BACKEND': 'django.core.files.storage.FileSystemStorage',
                'OPTIONS': {
                    'location': self.publico,
                    'base_url': '/media/',
                },
            },
            'private': {
                'BACKEND': 'django.core.files.storage.FileSystemStorage',
                'OPTIONS': {
                    'location': self.privado,
                    'base_url': None,
                },
            },
            'staticfiles': {
                'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
            },
        })
        self.override.enable()
        self.empresa = Empresa.objects.create(nome='Empresa NF-e A')
        self.outra_empresa = Empresa.objects.create(nome='Empresa NF-e B')
        self.base = Base.objects.create(nome='BASE NF-E A', empresa=self.empresa)
        self.admin = self._usuario('admin.nfe.a', self.empresa, Perfil.Role.ADMIN)
        self.outro_admin = self._usuario(
            'admin.nfe.b', self.outra_empresa, Perfil.Role.ADMIN,
        )
        self.gestor = self._usuario(
            'gestor.nfe.a', self.empresa, Perfil.Role.GESTOR, self.base,
        )
        self.jose = self._usuario(
            'jose.barboza', self.empresa, Perfil.Role.ADMIN,
        )
        self.fornecedor = FornecedorInsumo.objects.create(
            nome='Fornecedor NF-e', documento='32000000000101',
        )
        FornecedorEmpresa.objects.create(
            empresa=self.empresa,
            fornecedor=self.fornecedor,
            status=FornecedorEmpresa.Status.HOMOLOGADO,
            cadastrado_por=self.admin,
            homologado_por=self.admin,
        )
        categoria = CategoriaInsumo.objects.create(nome='Categoria NF-e')
        self.insumo = Insumo.objects.create(
            descricao='Insumo NF-e', categoria=categoria, unidade_medida='UN',
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

    @staticmethod
    def _pdf(nome='danfe.pdf', conteudo=b'%PDF-1.7\n%%EOF'):
        return SimpleUploadedFile(nome, conteudo, content_type='application/pdf')

    @staticmethod
    def _xml(nome='nfe.xml', conteudo=None):
        conteudo = conteudo or (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">'
            b'<NFe><infNFe Id="NFe35261032000000000101550010000001231123456789">'
            b'<ide><serie>1</serie><nNF>123</nNF><dhEmi>2026-10-29T10:00:00-03:00</dhEmi></ide>'
            b'<emit><CNPJ>32000000000101</CNPJ><xNome>Fornecedor NF-e</xNome></emit>'
            b'<det nItem="1"><prod><cProd>ABC</cProd><cEAN>SEM GTIN</cEAN>'
            b'<xProd>Insumo NF-e</xProd><NCM>39269090</NCM><CFOP>5102</CFOP>'
            b'<uCom>UN</uCom><qCom>2.0000</qCom><vUnCom>15.500000</vUnCom>'
            b'<vProd>31.00</vProd></prod></det>'
            b'<total><ICMSTot><vProd>31.00</vProd><vFrete>0</vFrete>'
            b'<vDesc>0</vDesc><vICMS>0</vICMS><vST>0</vST><vIPI>0</vIPI>'
            b'<vII>0</vII><vPIS>0</vPIS><vCOFINS>0</vCOFINS>'
            b'<vNF>31.00</vNF></ICMSTot></total>'
            b'</infNFe></NFe></nfeProc>'
        )
        return SimpleUploadedFile(nome, conteudo, content_type='application/xml')

    def _post_aquisicao(self, *, pdf=None, xml=None):
        dados = {
            'empresa': self.empresa.pk,
            'fornecedor': self.fornecedor.pk,
            'data_compra': date.today().isoformat(),
            'tipo_item': ItemAquisicao.Tipo.INSUMO,
            'insumo': self.insumo.pk,
            'produto': '',
            'quantidade': '2',
            'valor_unitario': '15.50',
            'desconto': '0',
            'frete': '0',
            'impostos': '0',
        }
        if pdf is not None:
            dados['arquivo_danfe_pdf'] = pdf
        if xml is not None:
            dados['arquivo_xml_nfe'] = xml
        self.client.force_login(self.admin)
        return self.client.post(reverse('compras:aquisicao_criar'), dados)

    def _aquisicao_com_documentos(self):
        resposta = self._post_aquisicao(pdf=self._pdf(), xml=self._xml())
        self.assertEqual(resposta.status_code, 302)
        return Aquisicao.objects.get()

    def test_upload_valido_grava_privado_com_nome_opaco(self):
        aquisicao = self._aquisicao_com_documentos()

        self.assertTrue(aquisicao.arquivo_danfe_pdf.name.startswith(
            f'compras/{self.empresa.pk}/danfe/',
        ))
        self.assertTrue(aquisicao.arquivo_xml_nfe.name.startswith(
            f'compras/{self.empresa.pk}/xml/',
        ))
        self.assertNotIn('danfe.pdf', aquisicao.arquivo_danfe_pdf.name)
        self.assertTrue((self.privado / aquisicao.arquivo_danfe_pdf.name).exists())
        self.assertTrue((self.privado / aquisicao.arquivo_xml_nfe.name).exists())
        self.assertFalse((self.publico / aquisicao.arquivo_danfe_pdf.name).exists())
        with self.assertRaisesMessage(ValueError, 'não possuem URL pública'):
            _ = aquisicao.arquivo_danfe_pdf.url

    def test_conteudo_disfarcado_xml_invalido_e_doctype_sao_rejeitados(self):
        pdf_invalido = self._post_aquisicao(
            pdf=self._pdf(conteudo=b'isto nao e pdf'),
        )
        self.assertContains(
            pdf_invalido,
            'O conteúdo enviado não corresponde a um PDF válido.',
        )
        xml_invalido = self._post_aquisicao(
            xml=self._xml(conteudo=b'<nfeProc>'),
        )
        self.assertContains(
            xml_invalido,
            'O arquivo XML da NF-e não está bem formado.',
        )
        xml_doctype = self._post_aquisicao(xml=self._xml(conteudo=(
            b'<!DOCTYPE foo [<!ENTITY x "segredo">]>'
            b'<nfeProc><NFe>&x;</NFe></nfeProc>'
        )))
        self.assertContains(
            xml_doctype,
            'O XML contém declarações não permitidas.',
        )
        self.assertFalse(Aquisicao.objects.exists())

    def test_download_revalida_perfil_empresa_e_headers(self):
        aquisicao = self._aquisicao_com_documentos()
        url = reverse('compras:aquisicao_documento', args=[aquisicao.pk, 'danfe'])

        self.client.force_login(self.admin)
        permitido = self.client.get(url)
        self.assertEqual(permitido.status_code, 200)
        self.assertEqual(permitido['Cache-Control'], 'private, no-store')
        self.assertEqual(permitido['X-Content-Type-Options'], 'nosniff')
        self.assertIn('attachment;', permitido['Content-Disposition'])
        self.assertEqual(b''.join(permitido.streaming_content), b'%PDF-1.7\n%%EOF')
        permitido.close()

        for usuario in (self.outro_admin, self.gestor, self.jose):
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                self.assertEqual(self.client.get(url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_storage_privado_le_documento_legado_sem_url_publica(self):
        nome_legado = 'compras/danfe/2026/10/legado.pdf'
        from django.core.files.storage import storages
        storages['default'].save(nome_legado, ContentFile(b'%PDF-1.4 legado'))
        aquisicao = AquisicaoService.criar(
            empresa=self.empresa,
            fornecedor=self.fornecedor,
            usuario=self.admin,
            arquivo_danfe_pdf=nome_legado,
            itens=[{
                'tipo_item': ItemAquisicao.Tipo.INSUMO,
                'insumo': self.insumo,
                'quantidade': Decimal('1'),
                'valor_unitario': Decimal('10'),
            }],
        )
        self.assertFalse((self.privado / nome_legado).exists())
        self.client.force_login(self.admin)
        resposta = self.client.get(reverse(
            'compras:aquisicao_documento', args=[aquisicao.pk, 'danfe'],
        ))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(b''.join(resposta.streaming_content), b'%PDF-1.4 legado')
        resposta.close()

