from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse

from compras.forms import CatalogoEmpresaForm
from compras.models import (
    CapacidadeCatalogoProdutoEmpresa,
    CatalogoProdutoEmpresa,
)
from estoque.forms import EquipamentoForm
from estoque.models import (
    Base,
    CategoriaEquipamentoEmpresa,
    Empresa,
    Equipamento,
    Perfil,
    Produto,
)
from estoque.services.ativo_capacidade_service import AtivoCapacidadeService


class AtivoCapacidadeServiceR4Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = Empresa.objects.create(nome='Empresa R4', slug='empresa-r4')
        cls.produto = Produto.objects.create(
            codigo='R4-001',
            descricao='Cadeira R4',
            fabricante='Fabricante',
            modelo='Modelo',
            categoria='Mobiliário',
            empresa_catalogo_origem=cls.empresa,
        )
        cls.catalogo = CatalogoProdutoEmpresa.objects.create(
            empresa=cls.empresa,
            produto=cls.produto,
            ativo=True,
        )

    def test_produto_legado_preserva_capacidades_atuais_sem_configuracao(self):
        self.assertTrue(AtivoCapacidadeService.habilitada(
            empresa=self.empresa,
            produto=self.produto,
            codigo=CapacidadeCatalogoProdutoEmpresa.PATRIMONIO_OBRIGATORIO,
        ))
        self.assertTrue(AtivoCapacidadeService.habilitada(
            empresa=self.empresa,
            produto=self.produto,
            codigo=CapacidadeCatalogoProdutoEmpresa.PERMITE_TRANSFERENCIA,
        ))
        self.assertFalse(AtivoCapacidadeService.habilitada(
            empresa=self.empresa,
            produto=self.produto,
            codigo=CapacidadeCatalogoProdutoEmpresa.CUSTODIA_PESSOAL,
        ))

    def test_configuracao_explicita_sobrepoe_padrao_legado(self):
        CapacidadeCatalogoProdutoEmpresa.objects.create(
            catalogo=self.catalogo,
            codigo=CapacidadeCatalogoProdutoEmpresa.PATRIMONIO_OBRIGATORIO,
            ativa=False,
        )
        self.assertFalse(AtivoCapacidadeService.habilitada(
            empresa=self.empresa,
            produto=self.produto,
            codigo=CapacidadeCatalogoProdutoEmpresa.PATRIMONIO_OBRIGATORIO,
        ))

    def test_lista_habilitada_respeita_padrao_e_configuracao_explicita(self):
        self.assertEqual(
            AtivoCapacidadeService.produtos_habilitados(
                empresa=self.empresa,
                codigo=CapacidadeCatalogoProdutoEmpresa.POSSUI_SERIE,
                produtos=[self.produto.pk],
            ),
            {self.produto.pk},
        )
        CapacidadeCatalogoProdutoEmpresa.objects.create(
            catalogo=self.catalogo,
            codigo=CapacidadeCatalogoProdutoEmpresa.POSSUI_SERIE,
            ativa=False,
        )
        self.assertEqual(
            AtivoCapacidadeService.produtos_habilitados(
                empresa=self.empresa,
                codigo=CapacidadeCatalogoProdutoEmpresa.POSSUI_SERIE,
                produtos=[self.produto.pk],
            ),
            set(),
        )

    def test_mesmo_produto_pode_ter_regra_diferente_em_outro_tenant(self):
        outra_empresa = Empresa.objects.create(
            nome='Outra Empresa R4', slug='outra-empresa-r4',
        )
        outro_catalogo = CatalogoProdutoEmpresa.objects.create(
            empresa=outra_empresa,
            produto=self.produto,
            ativo=True,
        )
        CapacidadeCatalogoProdutoEmpresa.objects.create(
            catalogo=self.catalogo,
            codigo=CapacidadeCatalogoProdutoEmpresa.POSSUI_IMEI,
            ativa=True,
        )
        CapacidadeCatalogoProdutoEmpresa.objects.create(
            catalogo=outro_catalogo,
            codigo=CapacidadeCatalogoProdutoEmpresa.POSSUI_IMEI,
            ativa=False,
        )
        self.assertTrue(AtivoCapacidadeService.identificadores(
            empresa=self.empresa,
            produto=self.produto,
        )['possui_imei'])
        self.assertFalse(AtivoCapacidadeService.identificadores(
            empresa=outra_empresa,
            produto=self.produto,
        )['possui_imei'])


class CatalogoEmpresaCapacidadesR4FormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = Empresa.objects.create(nome='Empresa Form R4', slug='empresa-form-r4')
        cls.superuser = User.objects.create_superuser(
            username='super-r4', email='super-r4@example.com', password='senha-teste',
        )
        cls.produto = Produto.objects.create(
            codigo='R4-FORM-001',
            descricao='Mesa R4',
            fabricante='Fabricante',
            modelo='Modelo',
            categoria='Mobiliário',
            empresa_catalogo_origem=cls.empresa,
        )

    def test_exigencia_deve_estar_contida_na_capacidade(self):
        form = CatalogoEmpresaForm(data={
            'empresa': self.empresa.pk,
            'produtos': [self.produto.pk],
            'produtos_patrimonio_obrigatorio': [self.produto.pk],
        }, user=self.superuser, empresa=self.empresa)
        self.assertFalse(form.is_valid())
        self.assertIn(
            'Todo item que exige patrimônio também deve permitir patrimônio.',
            form.non_field_errors(),
        )

    def test_salva_capacidades_por_empresa_no_catalogo(self):
        self.client.force_login(self.superuser)
        resposta = self.client.post(reverse('compras:catalogo_empresa'), {
            'empresa': self.empresa.pk,
            'produtos': [self.produto.pk],
            'produtos_individualizaveis': [self.produto.pk],
            'produtos_com_patrimonio': [self.produto.pk],
            'produtos_patrimonio_obrigatorio': [self.produto.pk],
            'produtos_com_serie': [self.produto.pk],
            'produtos_com_imei': [self.produto.pk],
            'produtos_sick': [self.produto.pk],
            'produtos_manutencao': [self.produto.pk],
            'produtos_transferencia': [self.produto.pk],
            'produtos_inativacao': [self.produto.pk],
        })
        self.assertEqual(resposta.status_code, 302)
        catalogo = CatalogoProdutoEmpresa.objects.get(
            empresa=self.empresa,
            produto=self.produto,
        )
        capacidades = dict(catalogo.capacidades.values_list('codigo', 'ativa'))
        self.assertTrue(capacidades[CapacidadeCatalogoProdutoEmpresa.POSSUI_PATRIMONIO])
        self.assertTrue(capacidades[CapacidadeCatalogoProdutoEmpresa.PATRIMONIO_OBRIGATORIO])
        self.assertTrue(capacidades[CapacidadeCatalogoProdutoEmpresa.POSSUI_SERIE])
        self.assertTrue(capacidades[CapacidadeCatalogoProdutoEmpresa.POSSUI_IMEI])
        self.assertFalse(capacidades[CapacidadeCatalogoProdutoEmpresa.SERIE_OBRIGATORIA])
        self.assertTrue(capacidades[CapacidadeCatalogoProdutoEmpresa.PERMITE_SICK])


class EquipamentoIdentificadoresFlexiveisR4Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = Empresa.objects.create(nome='Empresa Ativos R4', slug='ativos-r4')
        cls.base = Base.objects.create(empresa=cls.empresa, nome='Base R4')
        CategoriaEquipamentoEmpresa.objects.create(
            empresa=cls.empresa, nome='Mobiliário', ativo=True,
        )
        CategoriaEquipamentoEmpresa.objects.create(
            empresa=cls.empresa, nome='Informática', ativo=True,
        )
        CategoriaEquipamentoEmpresa.objects.create(
            empresa=cls.empresa, nome='Telefonia', ativo=True,
        )
        cls.usuario = User.objects.create_user(
            username='admin-ativos-r4', password='senha-teste',
        )
        perfil = cls.usuario.perfil
        perfil.empresa = cls.empresa
        perfil.role = Perfil.Role.ADMIN
        perfil.save()
        cls.cadeira = Produto.objects.create(
            codigo='R4-CADEIRA',
            descricao='Cadeira sem série',
            fabricante='Fabricante',
            modelo='Modelo',
            categoria='Mobiliário',
            empresa_catalogo_origem=cls.empresa,
        )
        cls.notebook = Produto.objects.create(
            codigo='R4-NOTEBOOK',
            descricao='Notebook legado',
            fabricante='Fabricante',
            modelo='Modelo',
            categoria='Informática',
            empresa_catalogo_origem=cls.empresa,
        )
        cls.celular = Produto.objects.create(
            codigo='R4-CELULAR',
            descricao='Celular corporativo',
            fabricante='Fabricante',
            modelo='Modelo',
            categoria='Telefonia',
            empresa_catalogo_origem=cls.empresa,
        )
        cls.catalogo_cadeira = CatalogoProdutoEmpresa.objects.create(
            empresa=cls.empresa, produto=cls.cadeira, ativo=True,
        )
        CatalogoProdutoEmpresa.objects.create(
            empresa=cls.empresa, produto=cls.notebook, ativo=True,
        )
        catalogo_celular = CatalogoProdutoEmpresa.objects.create(
            empresa=cls.empresa, produto=cls.celular, ativo=True,
        )
        for codigo, ativa in (
            (CapacidadeCatalogoProdutoEmpresa.POSSUI_SERIE, False),
            (CapacidadeCatalogoProdutoEmpresa.SERIE_OBRIGATORIA, False),
            (CapacidadeCatalogoProdutoEmpresa.POSSUI_PATRIMONIO, True),
            (CapacidadeCatalogoProdutoEmpresa.PATRIMONIO_OBRIGATORIO, False),
        ):
            CapacidadeCatalogoProdutoEmpresa.objects.create(
                catalogo=cls.catalogo_cadeira,
                codigo=codigo,
                ativa=ativa,
            )
        for codigo, ativa in (
            (CapacidadeCatalogoProdutoEmpresa.POSSUI_SERIE, False),
            (CapacidadeCatalogoProdutoEmpresa.SERIE_OBRIGATORIA, False),
            (CapacidadeCatalogoProdutoEmpresa.POSSUI_PATRIMONIO, False),
            (CapacidadeCatalogoProdutoEmpresa.PATRIMONIO_OBRIGATORIO, False),
            (CapacidadeCatalogoProdutoEmpresa.POSSUI_IMEI, True),
        ):
            CapacidadeCatalogoProdutoEmpresa.objects.create(
                catalogo=catalogo_celular,
                codigo=codigo,
                ativa=ativa,
            )

    def _form(self, produto, **dados_extras):
        dados = {
            'categoria': produto.categoria,
            'produto': produto.pk,
            'regional': self.base.pk,
            'finalidade': Equipamento.Finalidade.OPERACIONAL,
            'responsavel': '',
            'numero_serie': '',
            'patrimonio': '',
            'observacao_operacional': 'Unidade próxima à expedição',
        }
        dados.update(dados_extras)
        return EquipamentoForm(
            data=dados,
            user=self.usuario,
            base_selecionada=self.base,
        )

    def test_produto_configurado_aceita_identificadores_ausentes(self):
        form = self._form(self.cadeira)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        primeiro = form.save()
        segundo = self._form(self.cadeira)
        self.assertTrue(segundo.is_valid(), segundo.errors.as_json())
        segundo = segundo.save()
        self.assertIsNone(primeiro.numero_serie)
        self.assertIsNone(segundo.numero_serie)
        self.assertIsNone(primeiro.patrimonio)
        self.assertEqual(
            primeiro.observacao_operacional,
            'Unidade próxima à expedição'.upper(),
        )

    def test_produto_sem_serie_rejeita_serie_informada(self):
        form = self._form(self.cadeira, numero_serie='serie-invalida')
        self.assertFalse(form.is_valid())
        self.assertIn('numero_serie', form.errors)

    def test_produto_legado_continua_exigindo_serie_e_patrimonio(self):
        form = self._form(self.notebook)
        self.assertFalse(form.is_valid())
        self.assertIn('numero_serie', form.errors)
        self.assertIn('patrimonio', form.errors)

    def test_identificadores_informados_continuam_unicos(self):
        primeiro = self._form(self.cadeira, patrimonio='PAT-R4-001')
        self.assertTrue(primeiro.is_valid(), primeiro.errors.as_json())
        primeiro.save()
        duplicado = self._form(self.cadeira, patrimonio='pat-r4-001')
        self.assertFalse(duplicado.is_valid())
        self.assertIn('patrimonio', duplicado.errors)

    def test_imei_e_opcional_e_segundo_imei_tambem(self):
        sem_imei = self._form(self.celular)
        self.assertTrue(sem_imei.is_valid(), sem_imei.errors.as_json())
        sem_imei.save()
        com_imei = self._form(
            self.celular,
            imei_1='123456789012345',
            imei_2='543210987654321',
        )
        self.assertTrue(com_imei.is_valid(), com_imei.errors.as_json())

    def test_imei_deve_ter_15_digitos_e_ser_unico_entre_slots(self):
        invalido = self._form(self.celular, imei_1='123')
        self.assertFalse(invalido.is_valid())
        self.assertIn('imei_1', invalido.errors)
        primeiro = self._form(self.celular, imei_1='123456789012345')
        self.assertTrue(primeiro.is_valid(), primeiro.errors.as_json())
        primeiro.save()
        repetido_no_segundo_slot = self._form(
            self.celular,
            imei_2='123456789012345',
        )
        self.assertFalse(repetido_no_segundo_slot.is_valid())
        self.assertIn('imei_2', repetido_no_segundo_slot.errors)
