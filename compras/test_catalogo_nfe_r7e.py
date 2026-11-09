from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from compras.eventos import EventoCompraTipo
from compras.models import (
    CatalogoProdutoEmpresa,
    CodigoCatalogo,
    EventoCompra,
    FornecedorEmpresa,
    ItemAquisicao,
    ItemNotaFiscalAquisicao,
)
from compras.services import AquisicaoService
from estoque.models import Base, Empresa, Perfil, Produto
from insumos.models import CategoriaInsumo, FornecedorInsumo, Insumo


class CatalogoNFeR7ETests(TestCase):
    CHAVE = '35261032000000000101550010000004561123456780'
    EAN = '7891234567890'

    def setUp(self):
        self.diretorios = TemporaryDirectory(
            dir=settings.BASE_DIR,
            prefix='_test_catalogo_nfe_',
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
        self.empresa = Empresa.objects.create(nome='Empresa Catálogo NF-e')
        self.outra_empresa = Empresa.objects.create(nome='Outra Empresa Catálogo NF-e')
        self.base = Base.objects.create(nome='BASE CATÁLOGO', empresa=self.empresa)
        self.admin = self._usuario('admin.catalogo.nfe', self.empresa, Perfil.Role.ADMIN)
        self.gestor = self._usuario(
            'gestor.catalogo.nfe', self.empresa, Perfil.Role.GESTOR, self.base,
        )
        self.jose = self._usuario('jose.barboza', self.empresa, Perfil.Role.ADMIN)
        self.outro_admin = self._usuario(
            'admin.outro.catalogo.nfe', self.outra_empresa, Perfil.Role.ADMIN,
        )
        self.fornecedor = FornecedorInsumo.objects.create(
            nome='Fornecedor Catálogo', documento='32000000000101',
        )
        FornecedorEmpresa.objects.create(
            empresa=self.empresa,
            fornecedor=self.fornecedor,
            status=FornecedorEmpresa.Status.HOMOLOGADO,
            cadastrado_por=self.admin,
            homologado_por=self.admin,
        )
        categoria = CategoriaInsumo.objects.create(nome='Categoria Catálogo')
        self.insumo = Insumo.objects.create(
            descricao='Insumo da aquisição', categoria=categoria, unidade_medida='UN',
        )
        self.produto = Produto.objects.create(
            codigo='PROD-NFE',
            descricao='Produto catalogado',
            fabricante='Fabricante',
            modelo='Modelo',
            categoria='Categoria',
            empresa_catalogo_origem=self.empresa,
        )
        CatalogoProdutoEmpresa.objects.create(
            empresa=self.empresa,
            produto=self.produto,
            ativo=True,
            configurado_por=self.admin,
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
    def _xml(cls, *, descricao='Produto catalogado'):
        conteudo = f'''<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe>
<infNFe Id="NFe{cls.CHAVE}"><ide><serie>1</serie><nNF>456</nNF></ide>
<emit><CNPJ>32000000000101</CNPJ><xNome>Fornecedor Catálogo</xNome></emit>
<det nItem="1"><prod><cProd>FORN-456</cProd><cEAN>{cls.EAN}</cEAN>
<xProd>{descricao}</xProd><NCM>84713012</NCM><CFOP>5102</CFOP><uCom>UN</uCom>
<qCom>1</qCom><vUnCom>100</vUnCom><vProd>100</vProd></prod></det>
<total><ICMSTot><vProd>100</vProd><vNF>100</vNF></ICMSTot></total>
</infNFe></NFe></nfeProc>'''.encode()
        return SimpleUploadedFile('catalogo.xml', conteudo, content_type='application/xml')

    def _criar(self, *, descricao='Produto catalogado'):
        return AquisicaoService.criar(
            empresa=self.empresa,
            fornecedor=self.fornecedor,
            usuario=self.admin,
            arquivo_xml_nfe=self._xml(descricao=descricao),
            itens=[{
                'tipo_item': ItemAquisicao.Tipo.INSUMO,
                'insumo': self.insumo,
                'quantidade': Decimal('1'),
                'valor_unitario': Decimal('100'),
            }],
        )

    def test_codigo_exato_sugere_e_confirmacao_registra_codigo_fornecedor(self):
        codigo_ean = CodigoCatalogo.objects.create(
            empresa=self.empresa,
            produto=self.produto,
            tipo=CodigoCatalogo.Tipo.EAN_GTIN,
            codigo=self.EAN,
            criado_por=self.admin,
        )
        aquisicao = self._criar(descricao='Descrição diferente da cadastrada')
        item = aquisicao.nota_fiscal.itens.get()

        self.assertEqual(item.status_catalogo, ItemNotaFiscalAquisicao.StatusCatalogo.SUGERIDO)
        self.assertEqual(item.produto_catalogo, self.produto)
        self.assertEqual(item.codigo_catalogo, codigo_ean)
        self.assertFalse(CodigoCatalogo.objects.filter(
            empresa=self.empresa,
            tipo=CodigoCatalogo.Tipo.CODIGO_FORNECEDOR,
        ).exists())

        self.client.force_login(self.admin)
        url = reverse(
            'compras:aquisicao_confirmar_item_nfe_catalogo',
            args=[aquisicao.pk, item.pk],
        )
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(self.client.post(url).status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.status_catalogo, ItemNotaFiscalAquisicao.StatusCatalogo.CONFIRMADO)
        self.assertTrue(CodigoCatalogo.objects.filter(
            empresa=self.empresa,
            produto=self.produto,
            tipo=CodigoCatalogo.Tipo.CODIGO_FORNECEDOR,
            codigo='FORN-456',
        ).exists())
        self.assertEqual(EventoCompra.objects.filter(
            tipo=EventoCompraTipo.NFE_ITEM_CATALOGO_CONFIRMADO,
        ).count(), 1)

    def test_descricao_exata_apenas_sugere_ate_confirmacao_humana(self):
        aquisicao = self._criar()
        item = aquisicao.nota_fiscal.itens.get()

        self.assertEqual(item.status_catalogo, ItemNotaFiscalAquisicao.StatusCatalogo.SUGERIDO)
        self.assertEqual(item.criterio_catalogo, 'DESCRIÇÃO EXATA')
        self.assertEqual(item.produto_catalogo, self.produto)
        self.assertFalse(CodigoCatalogo.objects.filter(empresa=self.empresa).exists())

        self.client.force_login(self.admin)
        self.client.post(reverse(
            'compras:aquisicao_confirmar_item_nfe_catalogo',
            args=[aquisicao.pk, item.pk],
        ))
        self.assertEqual(CodigoCatalogo.objects.filter(empresa=self.empresa).count(), 2)

    def test_codigo_de_outra_empresa_nao_e_sugerido(self):
        produto_externo = Produto.objects.create(
            codigo='PROD-EXTERNO', descricao='Exclusivo', fabricante='Fabricante',
            modelo='Externo', categoria='Categoria',
            empresa_catalogo_origem=self.outra_empresa,
        )
        CodigoCatalogo.objects.create(
            empresa=self.outra_empresa,
            produto=produto_externo,
            tipo=CodigoCatalogo.Tipo.EAN_GTIN,
            codigo=self.EAN,
            criado_por=self.outro_admin,
        )
        aquisicao = self._criar(descricao='Item totalmente desconhecido')
        item = aquisicao.nota_fiscal.itens.get()

        self.assertEqual(
            item.status_catalogo,
            ItemNotaFiscalAquisicao.StatusCatalogo.NAO_ENCONTRADO,
        )
        self.assertIsNone(item.produto_catalogo)
        self.assertIsNone(item.insumo_catalogo)

    def test_gestor_jose_e_outra_empresa_nao_confirmam_sugestao(self):
        aquisicao = self._criar()
        item = aquisicao.nota_fiscal.itens.get()
        url = reverse(
            'compras:aquisicao_confirmar_item_nfe_catalogo',
            args=[aquisicao.pk, item.pk],
        )

        for usuario, status_esperado in (
            (self.gestor, 403),
            (self.jose, 403),
            (self.outro_admin, 404),
        ):
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                self.assertEqual(
                    self.client.post(url).status_code,
                    status_esperado,
                )
        item.refresh_from_db()
        self.assertEqual(item.status_catalogo, ItemNotaFiscalAquisicao.StatusCatalogo.SUGERIDO)

    def test_cadastro_assistido_de_equipamento_prefill_e_confirma_vinculo(self):
        aquisicao = self._criar(descricao='Equipamento novo da nota')
        item = aquisicao.nota_fiscal.itens.get()
        url = reverse('compras:criar_produto_catalogo')
        url = f'{url}?aquisicao={aquisicao.pk}&item_nfe={item.pk}'
        self.client.force_login(self.admin)

        pagina = self.client.get(url)
        self.assertEqual(pagina.status_code, 200)
        form = pagina.context['form']
        self.assertEqual(form.initial['descricao'], 'Equipamento novo da nota')
        self.assertEqual(
            list(form.fields['empresa_catalogo'].queryset),
            [self.empresa],
        )
        self.assertFalse(Produto.objects.filter(descricao='Equipamento novo da nota').exists())

        resposta = self.client.post(url, {
            'empresa_catalogo': self.empresa.pk,
            'codigo': 'FORN-456',
            'descricao': 'Equipamento novo da nota',
            'nome_resumido': 'Equipamento novo',
            'fabricante': 'Fabricante revisado',
            'modelo': 'Modelo revisado',
            'sku_fabricante': 'FORN-456',
            'categoria': 'Categoria revisada',
            'subcategoria': '',
            'unidade_medida': 'UN',
            'quantidade_embalagem': '1',
            'especificacoes_tecnicas': '{}',
            'ativo': 'on',
        })
        self.assertRedirects(
            resposta,
            reverse('compras:aquisicao_detalhe', args=[aquisicao.pk]),
        )
        novo = Produto.objects.get(descricao__iexact='Equipamento novo da nota')
        item.refresh_from_db()
        self.assertEqual(item.produto_catalogo, novo)
        self.assertEqual(item.status_catalogo, ItemNotaFiscalAquisicao.StatusCatalogo.CONFIRMADO)

    def test_cadastro_assistido_de_insumo_exige_base_e_confirma_vinculo(self):
        aquisicao = self._criar(descricao='Insumo novo da nota')
        aquisicao.base_destino = self.base
        aquisicao.save(update_fields=['base_destino', 'atualizado_em'])
        item = aquisicao.nota_fiscal.itens.get()
        url = reverse('insumos:criar_item_insumo')
        url = f'{url}?aquisicao={aquisicao.pk}&item_nfe={item.pk}'
        self.client.force_login(self.admin)

        pagina = self.client.get(url)
        self.assertEqual(pagina.status_code, 200)
        form = pagina.context['form']
        self.assertEqual(form.initial['descricao'], 'Insumo novo da nota')
        self.assertTrue(form.fields['base_lote'].required)
        self.assertEqual(
            list(form.fields['base_lote'].queryset),
            [self.base],
        )
        self.assertFalse(Insumo.objects.filter(descricao='Insumo novo da nota').exists())

        resposta = self.client.post(url, {
            'descricao': 'Insumo novo da nota',
            'termo_pesquisa_online': 'Insumo novo da nota',
            'categoria': self.insumo.categoria_id,
            'unidade_medida': 'UN',
            'natureza': Insumo.Natureza.CONSUMIVEL,
            'forma_controle': Insumo.FormaControle.QUANTIDADE,
            'base_lote': self.base.pk,
            'estoque_minimo': '2.00',
            'estoque_maximo': '',
            'ativo': 'on',
        })
        self.assertRedirects(
            resposta,
            reverse('compras:aquisicao_detalhe', args=[aquisicao.pk]),
        )
        novo = Insumo.objects.get(descricao__iexact='Insumo novo da nota')
        item.refresh_from_db()
        self.assertEqual(item.insumo_catalogo, novo)
        self.assertEqual(item.status_catalogo, ItemNotaFiscalAquisicao.StatusCatalogo.CONFIRMADO)

    def test_cadastro_assistido_bloqueia_usuario_sem_acesso_ao_documento(self):
        aquisicao = self._criar(descricao='Item novo protegido')
        item = aquisicao.nota_fiscal.itens.get()
        url_equipamento = reverse('compras:criar_produto_catalogo')
        url_equipamento = (
            f'{url_equipamento}?aquisicao={aquisicao.pk}&item_nfe={item.pk}'
        )
        url_insumo = reverse('insumos:criar_item_insumo')
        url_insumo = f'{url_insumo}?aquisicao={aquisicao.pk}&item_nfe={item.pk}'

        for usuario, status_equipamento in (
            (self.gestor, 403),
            (self.jose, 403),
            (self.outro_admin, 404),
        ):
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                self.assertEqual(
                    self.client.get(url_equipamento).status_code,
                    status_equipamento,
                )
                self.assertEqual(self.client.get(url_insumo).status_code, 404)
