from datetime import date, timedelta

from django.test import TestCase

from estoque.models import Base, Empresa
from insumos.models import (
    CategoriaInsumo,
    CertificadoEpi,
    Insumo,
    LoteEpi,
    ProdutoEpi,
)
from insumos.services.alerta_epi_service import AlertaEpiService


class AlertasEpiR3DTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        categoria = CategoriaInsumo.objects.create(nome='EPI Alertas R3D')
        insumo = Insumo.objects.create(
            descricao='Capacete Alertas R3D',
            categoria=categoria,
            unidade_medida='UN',
            natureza=Insumo.Natureza.EPI,
            forma_controle=Insumo.FormaControle.LOTE,
        )
        cls.produto = ProdutoEpi.objects.create(insumo=insumo)
        empresa = Empresa.objects.create(nome='Empresa Alertas R3D')
        cls.base = Base.objects.create(nome='Base Alertas R3D', empresa=empresa)
        cls.referencia = date(2026, 10, 16)

    def _certificado(self, dias):
        self.produto.certificados.all().delete()
        return CertificadoEpi.objects.create(
            produto_epi=self.produto,
            numero_ca=f'CA-{dias}',
            validade_ca=self.referencia + timedelta(days=dias),
        )

    def test_ca_inexistente(self):
        estado = AlertaEpiService.estado_ca(
            produto_epi=self.produto,
            referencia=self.referencia,
        )
        self.assertEqual(estado.codigo, AlertaEpiService.CA_INEXISTENTE)

    def test_faixas_de_alerta_do_ca(self):
        for dias, faixa in ((90, 90), (60, 60), (30, 30)):
            self._certificado(dias)
            estado = AlertaEpiService.estado_ca(
                produto_epi=self.produto,
                referencia=self.referencia,
            )
            self.assertEqual(estado.codigo, AlertaEpiService.CA_PROXIMO)
            self.assertEqual(estado.faixa_dias, faixa)

    def test_ca_valido_e_vencido(self):
        self._certificado(91)
        self.assertEqual(
            AlertaEpiService.estado_ca(
                produto_epi=self.produto, referencia=self.referencia,
            ).codigo,
            AlertaEpiService.CA_VALIDO,
        )
        self._certificado(-1)
        self.assertEqual(
            AlertaEpiService.estado_ca(
                produto_epi=self.produto, referencia=self.referencia,
            ).codigo,
            AlertaEpiService.CA_VENCIDO,
        )

    def test_validade_fisica_proxima_e_epi_vencido(self):
        lote = LoteEpi.objects.create(
            base=self.base,
            produto_epi=self.produto,
            codigo_lote='LOTE-ALERTA',
            validade_fisica=self.referencia + timedelta(days=30),
        )
        for dias, faixa in ((90, 90), (60, 60), (30, 30)):
            lote.validade_fisica = self.referencia + timedelta(days=dias)
            proximo = AlertaEpiService.estado_validade_fisica(
                lote=lote, referencia=self.referencia,
            )
            self.assertEqual(proximo.codigo, AlertaEpiService.VALIDADE_FISICA_PROXIMA)
            self.assertEqual(proximo.faixa_dias, faixa)

        lote.validade_fisica = self.referencia - timedelta(days=1)
        vencido = AlertaEpiService.estado_validade_fisica(
            lote=lote, referencia=self.referencia,
        )
        self.assertEqual(vencido.codigo, AlertaEpiService.EPI_VENCIDO)

    def test_ca_divergente_no_lote_e_identificado(self):
        outro_insumo = Insumo.objects.create(
            descricao='Outro EPI Alertas R3D',
            categoria=self.produto.insumo.categoria,
            unidade_medida='UN',
            natureza=Insumo.Natureza.EPI,
            forma_controle=Insumo.FormaControle.LOTE,
        )
        outro_produto = ProdutoEpi.objects.create(insumo=outro_insumo)
        certificado_divergente = CertificadoEpi.objects.create(
            produto_epi=outro_produto,
            numero_ca='CA-DIVERGENTE-R3D',
        )
        lote = LoteEpi.objects.create(
            base=self.base,
            produto_epi=self.produto,
            certificado=certificado_divergente,
            codigo_lote='LOTE-DIVERGENTE',
        )

        estado = AlertaEpiService.estado_ca(
            lote=lote, referencia=self.referencia,
        )

        self.assertEqual(estado.codigo, AlertaEpiService.CA_DIVERGENTE)

    def test_validade_fisica_continua_opcional(self):
        lote = LoteEpi.objects.create(
            base=self.base,
            produto_epi=self.produto,
            codigo_lote='LOTE-SEM-VALIDADE',
        )
        estado = AlertaEpiService.estado_validade_fisica(
            lote=lote, referencia=self.referencia,
        )
        self.assertEqual(estado.codigo, AlertaEpiService.SEM_VALIDADE_FISICA)
