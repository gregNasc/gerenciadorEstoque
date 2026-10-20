from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from estoque.models import Base, Empresa
from insumos.models import (
    CategoriaInsumo,
    CertificadoEpi,
    Insumo,
    LoteEpi,
    ProdutoEpi,
    VarianteEpi,
)
from insumos.services.certificado_epi_service import CertificadoEpiService


class CertificadoEpiR3CTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        categoria = CategoriaInsumo.objects.create(nome='EPI R3C')
        insumo = Insumo.objects.create(
            descricao='Luva R3C',
            categoria=categoria,
            unidade_medida='PAR',
            natureza=Insumo.Natureza.EPI,
            forma_controle=Insumo.FormaControle.LOTE,
        )
        outro_insumo = Insumo.objects.create(
            descricao='Bota R3C',
            categoria=categoria,
            unidade_medida='PAR',
            natureza=Insumo.Natureza.EPI,
            forma_controle=Insumo.FormaControle.LOTE,
        )
        cls.produto = ProdutoEpi.objects.create(
            insumo=insumo,
            fabricante_importador='Fabricante R3C',
        )
        cls.outro_produto = ProdutoEpi.objects.create(
            insumo=outro_insumo,
            fabricante_importador='Outro fabricante R3C',
        )
        cls.variante_p = VarianteEpi.objects.create(
            produto_epi=cls.produto,
            nome='Luva',
            tamanho='P',
        )
        cls.variante_g = VarianteEpi.objects.create(
            produto_epi=cls.produto,
            nome='Luva',
            tamanho='G',
        )
        empresa = Empresa.objects.create(nome='Empresa R3C')
        cls.base = Base.objects.create(nome='Base R3C', empresa=empresa)

    def test_registro_normaliza_e_reutiliza_o_mesmo_ca(self):
        primeiro = CertificadoEpiService.registrar(
            produto_epi=self.produto,
            numero_ca=' ca-12345 ',
            validade_ca=date(2028, 6, 30),
        )
        segundo = CertificadoEpiService.registrar(
            produto_epi=self.produto,
            numero_ca='CA-12345',
            validade_ca=date(2029, 6, 30),
        )

        self.assertEqual(primeiro.pk, segundo.pk)
        self.assertEqual(CertificadoEpi.objects.count(), 1)
        self.assertEqual(segundo.numero_ca, 'CA-12345')
        self.assertEqual(segundo.validade_ca, date(2029, 6, 30))

    def test_variantes_compartilham_certificado_do_produto(self):
        certificado = CertificadoEpiService.registrar(
            produto_epi=self.produto,
            numero_ca='CA-VARIANTES',
        )

        self.assertEqual(self.variante_p.produto_epi, certificado.produto_epi)
        self.assertEqual(self.variante_g.produto_epi, certificado.produto_epi)
        self.assertEqual(self.produto.certificados.count(), 1)

    def test_ca_nao_pode_ser_recriado_em_outro_produto(self):
        CertificadoEpiService.registrar(
            produto_epi=self.produto,
            numero_ca='CA-EXCLUSIVO',
        )

        with self.assertRaises(ValidationError):
            CertificadoEpiService.registrar(
                produto_epi=self.outro_produto,
                numero_ca=' ca-exclusivo ',
            )

    def test_numero_ca_vazio_e_rejeitado(self):
        with self.assertRaises(ValidationError):
            CertificadoEpiService.registrar(
                produto_epi=self.produto,
                numero_ca='   ',
            )

    def test_validade_fisica_do_lote_nao_altera_validade_do_ca(self):
        certificado = CertificadoEpiService.registrar(
            produto_epi=self.produto,
            numero_ca='CA-VALIDADES',
            validade_ca=date(2028, 1, 31),
        )
        lote = LoteEpi.objects.create(
            base=self.base,
            produto_epi=self.produto,
            certificado=certificado,
            codigo_lote='LOTE-R3C',
            validade_fisica=date(2027, 1, 31),
        )

        lote.validade_fisica = date(2027, 12, 31)
        lote.save(update_fields=['validade_fisica', 'atualizado_em'])
        certificado.refresh_from_db()

        self.assertEqual(certificado.validade_ca, date(2028, 1, 31))
        self.assertEqual(lote.validade_fisica, date(2027, 12, 31))
