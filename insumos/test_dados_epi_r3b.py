from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from estoque.models import Base, Empresa, Perfil
from insumos.models import (
    CategoriaInsumo,
    CertificadoEpi,
    Insumo,
    LoteEpi,
    ProdutoEpi,
    VarianteEpi,
)
from insumos.policies import InsumosTenantPolicy


class DadosEpiR3BTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa_a = Empresa.objects.create(nome='Empresa EPI R3B A')
        cls.empresa_b = Empresa.objects.create(nome='Empresa EPI R3B B')
        cls.base_a = Base.objects.create(nome='Base EPI R3B A', empresa=cls.empresa_a)
        cls.base_b = Base.objects.create(nome='Base EPI R3B B', empresa=cls.empresa_b)
        cls.admin_a = User.objects.create_user('admin.epi.r3b')
        cls.admin_a.perfil.role = Perfil.Role.ADMIN
        cls.admin_a.perfil.empresa = cls.empresa_a
        cls.admin_a.perfil.save(update_fields=('role', 'empresa'))

        categoria = CategoriaInsumo.objects.create(nome='EPI R3B')
        cls.insumo_epi = Insumo.objects.create(
            descricao='Capacete EPI R3B',
            categoria=categoria,
            unidade_medida='UN',
            natureza=Insumo.Natureza.EPI,
            forma_controle=Insumo.FormaControle.LOTE,
        )
        cls.insumo_epi_2 = Insumo.objects.create(
            descricao='Bota EPI R3B',
            categoria=categoria,
            unidade_medida='PAR',
            natureza=Insumo.Natureza.EPI,
            forma_controle=Insumo.FormaControle.LOTE,
        )
        cls.insumo_comum = Insumo.objects.create(
            descricao='Papel comum R3B',
            categoria=categoria,
            unidade_medida='UN',
        )
        cls.produto = ProdutoEpi.objects.create(
            insumo=cls.insumo_epi,
            fabricante_importador='Fabricante R3B',
            observacao='Produto controlado',
        )
        cls.outro_produto = ProdutoEpi.objects.create(
            insumo=cls.insumo_epi_2,
            fabricante_importador='Outro Fabricante R3B',
        )
        cls.certificado = CertificadoEpi.objects.create(
            produto_epi=cls.produto,
            numero_ca='ca-r3b-001',
            validade_ca=date(2028, 1, 31),
        )
        cls.variante_p = VarianteEpi.objects.create(
            produto_epi=cls.produto,
            nome='Capacete padrão',
            tamanho='P',
            codigo='CAP-P',
        )
        cls.variante_g = VarianteEpi.objects.create(
            produto_epi=cls.produto,
            nome='Capacete padrão',
            tamanho='G',
            codigo='CAP-G',
        )

    def test_apenas_insumo_epi_recebe_dados_especializados(self):
        dados = ProdutoEpi(
            insumo=self.insumo_comum,
            fabricante_importador='Fabricante inválido',
        )

        with self.assertRaises(ValidationError) as contexto:
            dados.full_clean()

        self.assertIn('insumo', contexto.exception.message_dict)

    def test_um_ca_atende_multiplas_variantes_sem_duplicacao(self):
        self.assertEqual(self.produto.certificados.count(), 1)
        self.assertEqual(self.produto.variantes.count(), 2)
        self.assertEqual(self.variante_p.produto_epi, self.certificado.produto_epi)
        self.assertEqual(self.variante_g.produto_epi, self.certificado.produto_epi)
        self.assertEqual(self.certificado.numero_ca, 'CA-R3B-001')

    def test_numero_ca_e_unico_e_normalizado(self):
        with self.assertRaises(ValidationError):
            CertificadoEpi.objects.create(
                produto_epi=self.outro_produto,
                numero_ca=' ca-r3b-001 ',
            )

    def test_validade_fisica_e_independente_da_validade_do_ca(self):
        lote = LoteEpi(
            base=self.base_a,
            produto_epi=self.produto,
            variante=self.variante_p,
            certificado=self.certificado,
            codigo_lote=' lote-2026-01 ',
            fabricado_em=date(2026, 1, 10),
            validade_fisica=date(2027, 1, 10),
        )
        lote.full_clean()
        lote.save()

        self.assertEqual(lote.codigo_lote, 'LOTE-2026-01')
        self.assertEqual(lote.validade_fisica, date(2027, 1, 10))
        self.assertEqual(lote.certificado.validade_ca, date(2028, 1, 31))

    def test_lote_recusa_variante_e_certificado_de_outro_produto(self):
        outra_variante = VarianteEpi.objects.create(
            produto_epi=self.outro_produto,
            nome='Bota padrão',
            tamanho='40',
        )
        outro_certificado = CertificadoEpi.objects.create(
            produto_epi=self.outro_produto,
            numero_ca='CA-R3B-002',
        )
        lote = LoteEpi(
            base=self.base_a,
            produto_epi=self.produto,
            variante=outra_variante,
            certificado=outro_certificado,
            codigo_lote='LOTE-CRUZADO',
        )

        with self.assertRaises(ValidationError) as contexto:
            lote.full_clean()

        self.assertIn('variante', contexto.exception.message_dict)
        self.assertIn('certificado', contexto.exception.message_dict)

    def test_lote_recusa_validade_anterior_a_fabricacao(self):
        lote = LoteEpi(
            base=self.base_a,
            produto_epi=self.produto,
            codigo_lote='LOTE-DATA-INVALIDA',
            fabricado_em=date(2027, 1, 1),
            validade_fisica=date(2026, 12, 31),
        )

        with self.assertRaises(ValidationError) as contexto:
            lote.full_clean()

        self.assertIn('validade_fisica', contexto.exception.message_dict)

    def test_lotes_sao_isolados_por_tenant(self):
        lote_a = LoteEpi.objects.create(
            base=self.base_a,
            produto_epi=self.produto,
            codigo_lote='LOTE-A',
        )
        LoteEpi.objects.create(
            base=self.base_b,
            produto_epi=self.produto,
            codigo_lote='LOTE-B',
        )

        visiveis = InsumosTenantPolicy.epi_lots(
            self.admin_a,
            LoteEpi.objects.all(),
        )

        self.assertEqual(list(visiveis), [lote_a])
