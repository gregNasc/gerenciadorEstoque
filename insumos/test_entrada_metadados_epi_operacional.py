from django.contrib.auth.models import User
from django.db.models import Sum
from django.test import TestCase
from django.urls import reverse

from estoque.models import Base, Empresa, Perfil
from insumos.models import (
    AtivoInsumoIndividualizado,
    CategoriaInsumo,
    CertificadoEpi,
    Insumo,
    LoteEpi,
    MovimentacaoInsumo,
    VarianteEpi,
)


class EntradaMetadadosEpiOperacionalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = Empresa.objects.create(nome='Empresa Entrada Metadados')
        cls.base = Base.objects.create(nome='Base Entrada Metadados', empresa=cls.empresa)
        cls.admin = User.objects.create_user('admin.entrada.metadados', password='senha')
        cls.admin.perfil.empresa = cls.empresa
        cls.admin.perfil.role = Perfil.Role.ADMIN
        cls.admin.perfil.save(update_fields=['empresa', 'role'])
        cls.categoria_epi = CategoriaInsumo.objects.create(nome='EPI Entrada')
        cls.categoria_operacional = CategoriaInsumo.objects.create(nome='Operacional')
        cls.botas = Insumo.objects.create(
            descricao='Botas', categoria=cls.categoria_epi, unidade_medida='PAR',
            natureza=Insumo.Natureza.EPI,
            forma_controle=Insumo.FormaControle.LOTE,
        )
        cls.capacete = Insumo.objects.create(
            descricao='Capacete', categoria=cls.categoria_epi, unidade_medida='UN',
            natureza=Insumo.Natureza.EPI,
            forma_controle=Insumo.FormaControle.LOTE,
        )
        cls.escada = Insumo.objects.create(
            descricao='Escada', categoria=cls.categoria_operacional, unidade_medida='UN',
            natureza=Insumo.Natureza.CONSUMIVEL,
            forma_controle=Insumo.FormaControle.QUANTIDADE,
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def _dados(self, insumo, quantidade='1'):
        return {
            'base': self.base.pk,
            'categoria': insumo.categoria_id,
            'insumo': insumo.pk,
            'quantidade': quantidade,
        }

    def test_entrada_de_botas_vincula_tamanho_ca_lote_e_validades(self):
        dados = self._dados(self.botas, '3')
        dados.update({
            'numero_ca': 'CA-BOTA-37',
            'validade_ca': '2030-12-31',
            'tamanho_bota': '37',
            'codigo_lote': 'LOTE-BOTA-37',
            'fabricado_em': '2026-10-01',
            'validade_fisica': '2028-10-01',
        })

        resposta = self.client.post(reverse('insumos:cadastrar_insumos'), dados)

        self.assertEqual(resposta.status_code, 302)
        movimento = MovimentacaoInsumo.objects.get(insumo=self.botas)
        self.assertEqual(movimento.quantidade, 3)
        self.assertIsNotNone(movimento.lote_epi)
        self.assertEqual(movimento.lote_epi.variante.tamanho, '37')
        self.assertEqual(movimento.lote_epi.certificado.numero_ca, 'CA-BOTA-37')
        self.assertEqual(movimento.lote_epi.codigo_lote, 'LOTE-BOTA-37')
        self.assertEqual(str(movimento.lote_epi.validade_fisica), '2028-10-01')

    def test_mesmo_ca_aceita_varias_entradas_e_tamanhos_na_mesma_base(self):
        for quantidade, tamanho in (('6', '35'), ('2', '35'), ('7', '36')):
            dados = self._dados(self.botas, quantidade)
            dados.update({
                'numero_ca': '32807',
                'validade_ca': '2030-12-31',
                'tamanho_bota': tamanho,
                'codigo_lote': '',
            })
            resposta = self.client.post(reverse('insumos:cadastrar_insumos'), dados)
            self.assertEqual(resposta.status_code, 302)

        self.assertEqual(CertificadoEpi.objects.filter(numero_ca='32807').count(), 1)
        self.assertEqual(VarianteEpi.objects.filter(
            produto_epi__insumo=self.botas,
        ).count(), 2)
        self.assertEqual(LoteEpi.objects.filter(
            base=self.base,
            produto_epi__insumo=self.botas,
        ).count(), 2)
        self.assertEqual(
            MovimentacaoInsumo.objects.filter(insumo=self.botas).aggregate(
                total=Sum('quantidade'),
            )['total'],
            15,
        )

    def test_todo_epi_exige_ca_e_tamanho_ou_variante(self):
        dados = self._dados(self.capacete)

        resposta = self.client.post(reverse('insumos:cadastrar_insumos'), dados)

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Informe o CA do EPI.')
        self.assertContains(resposta, 'Informe o tamanho ou a variante do EPI.')
        self.assertFalse(MovimentacaoInsumo.objects.filter(insumo=self.capacete).exists())

    def test_epi_nao_numerico_aceita_variante(self):
        dados = self._dados(self.capacete, '2')
        dados.update({'numero_ca': 'CA-CAPACETE-M', 'tamanho_variante': 'M'})

        resposta = self.client.post(reverse('insumos:cadastrar_insumos'), dados)

        self.assertEqual(resposta.status_code, 302)
        movimento = MovimentacaoInsumo.objects.get(insumo=self.capacete)
        self.assertEqual(movimento.lote_epi.variante.tamanho, 'M')

    def test_operacional_pode_cadastrar_patrimonio_com_quantidade_um(self):
        dados = self._dados(self.escada)
        dados['patrimonio'] = 'PAT-ESCADA-ENTRADA-001'

        resposta = self.client.post(reverse('insumos:cadastrar_insumos'), dados)

        self.assertEqual(resposta.status_code, 302)
        movimento = MovimentacaoInsumo.objects.get(insumo=self.escada)
        self.assertEqual(
            movimento.ativo_individualizado.patrimonio,
            'PAT-ESCADA-ENTRADA-001',
        )
        self.escada.refresh_from_db()
        self.assertEqual(self.escada.natureza, Insumo.Natureza.REUTILIZAVEL)
        self.assertEqual(
            self.escada.forma_controle,
            Insumo.FormaControle.INDIVIDUALIZADO,
        )

    def test_patrimonio_exige_uma_unidade(self):
        dados = self._dados(self.escada, '2')
        dados['patrimonio'] = 'PAT-ESCADA-ENTRADA-002'

        resposta = self.client.post(reverse('insumos:cadastrar_insumos'), dados)

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(
            resposta,
            'A quantidade deve ser 1 quando um patrimônio for informado.',
        )
        self.assertFalse(AtivoInsumoIndividualizado.objects.exists())
        self.assertFalse(MovimentacaoInsumo.objects.filter(insumo=self.escada).exists())

    def test_api_informa_campos_condicionais_sem_expor_outro_dado(self):
        resposta = self.client.get(
            reverse('insumos:insumos_por_categoria'),
            {'categoria': self.categoria_epi.pk},
        )

        self.assertEqual(resposta.status_code, 200)
        itens = {item['descricao']: item for item in resposta.json()['insumos']}
        self.assertTrue(itens['Botas']['epi'])
        self.assertTrue(itens['Botas']['bota'])
        self.assertFalse(itens['CAPACETE']['bota'])
