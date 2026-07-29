from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from estoque.models import Empresa, Perfil
from insumos.models import (
    CategoriaInsumo,
    FornecedorInsumo,
    Insumo,
    OfertaPrecoOnline,
    PrecoFornecedorInsumo,
    PesquisaPrecoOnline,
)
from insumos.services.preco_online_service import (
    FidelityProvider,
    GimbaProvider,
    PrecoOnlineService,
)


class CatalogosFornecedoresTests(SimpleTestCase):
    def test_fidelity_extrai_produto_e_preco_publico(self):
        html = '''
            <a href="/produto/papel-a4/"><img src="papel.jpg"></a>
            <a href="/produto/papel-a4/">Papel sulfite A4 - Pct 500 folhas</a>
            <a href="/produto/papel-a4/">R$28.90</a>
        '''

        ofertas = FidelityProvider._extrair_ofertas(html, limite=20)

        self.assertEqual(len(ofertas), 1)
        self.assertEqual(ofertas[0]['codigo_externo'], 'papel-a4')
        self.assertEqual(ofertas[0]['preco'], Decimal('28.90'))
        self.assertEqual(ofertas[0]['fonte'], 'FIDELITY')

    def test_gimba_extrai_pid_e_preco_normal_sem_usar_preco_pix(self):
        html = '''
            <a href="/?PID=2502">Papel Sulfite A4 75g 500 Folhas</a>
            <a href="/?PID=2502">por apenas R$ 34,50 R$ 33,47 no PIX</a>
        '''

        ofertas = GimbaProvider._extrair_ofertas(html, limite=20)

        self.assertEqual(len(ofertas), 1)
        self.assertEqual(ofertas[0]['codigo_externo'], '2502')
        self.assertEqual(ofertas[0]['preco'], Decimal('34.50'))
        self.assertEqual(ofertas[0]['fonte'], 'GIMBA')


class UsarOfertaComoPrecoTests(TestCase):
    def setUp(self):
        empresa = Empresa.objects.create(nome='Empresa preço online')
        self.usuario = User.objects.create_user('admin_preco_online', password='teste')
        Perfil.objects.update_or_create(
            user=self.usuario,
            defaults={'empresa': empresa, 'role': Perfil.Role.ADMIN},
        )
        categoria = CategoriaInsumo.objects.create(nome='Papelaria online')
        self.insumo = Insumo.objects.create(
            descricao='Papel sulfite A4',
            categoria=categoria,
            unidade_medida='PCT',
        )
        self.fornecedor, _ = FornecedorInsumo.objects.update_or_create(
            documento='17829173000110',
            defaults={
                'nome': 'Fidelity Suprimentos',
                'site': 'https://fidelitysuprimentos.com.br/',
                'fonte_online': 'FIDELITY',
            },
        )
        pesquisa = PesquisaPrecoOnline.objects.create(
            insumo=self.insumo,
            termo='papel sulfite a4',
            fonte='FIDELITY',
            pesquisado_por=self.usuario,
        )
        self.oferta = OfertaPrecoOnline.objects.create(
            pesquisa=pesquisa,
            insumo=self.insumo,
            fonte='FIDELITY',
            codigo_externo='papel-a4',
            titulo='Papel sulfite A4 - pacote 500 folhas',
            vendedor='Fidelity Suprimentos',
            url='https://fidelitysuprimentos.com.br/produto/papel-a4/',
            preco=Decimal('28.90'),
            preco_total=Decimal('28.90'),
            frete_conhecido=False,
            condicao='novo',
        )
        self.preco_anterior = PrecoFornecedorInsumo.objects.create(
            insumo=self.insumo,
            fornecedor=self.fornecedor,
            valor_unitario=Decimal('30.00'),
            cadastrado_por=self.usuario,
        )
        self.client.force_login(self.usuario)

    def test_post_aplica_oferta_e_preserva_historico_anterior(self):
        resposta = self.client.post(reverse(
            'insumos:usar_oferta_como_preco',
            args=[self.oferta.pk],
        ))

        self.assertEqual(resposta.status_code, 302)
        self.preco_anterior.refresh_from_db()
        self.insumo.refresh_from_db()
        self.assertFalse(self.preco_anterior.ativo)
        self.assertEqual(self.insumo.valor_medio, Decimal('28.90'))
        self.assertEqual(self.insumo.preco_referencia.valor_unitario, Decimal('28.9000'))
        self.assertEqual(self.insumo.preco_referencia.fornecedor, self.fornecedor)

    def test_get_nao_aplica_oferta(self):
        resposta = self.client.get(reverse(
            'insumos:usar_oferta_como_preco',
            args=[self.oferta.pk],
        ))

        self.assertEqual(resposta.status_code, 405)
        self.insumo.refresh_from_db()
        self.assertEqual(self.insumo.valor_medio, Decimal('0'))

    @patch.object(GimbaProvider, 'buscar')
    def test_pesquisa_respeita_fornecedor_selecionado(self, buscar):
        buscar.return_value = [{
            'fonte': 'GIMBA',
            'codigo_externo': '2502',
            'titulo': 'Papel sulfite A4 500 folhas',
            'vendedor': 'Gimba',
            'url': 'https://www.gimba.com.br/?PID=2502',
            'preco': Decimal('34.50'),
            'frete': None,
            'preco_total': Decimal('34.50'),
            'frete_conhecido': False,
            'condicao': 'novo',
        }]

        pesquisa = PrecoOnlineService.pesquisar(
            insumo=self.insumo,
            termo='papel sulfite a4',
            usuario=self.usuario,
            fonte='GIMBA',
        )

        buscar.assert_called_once_with('papel sulfite a4')
        self.assertEqual(pesquisa.fonte, 'GIMBA')
        self.assertEqual(pesquisa.ofertas.get().codigo_externo, '2502')
