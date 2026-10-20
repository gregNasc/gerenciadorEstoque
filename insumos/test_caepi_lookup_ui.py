from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(CAEPI_API_URL='')
class CaepiLookupUiTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin-caepi-ui',
            email='admin@example.com',
            password='senha-teste',
        )
        self.client.force_login(self.admin)

    def test_endpoint_sem_api_indica_consulta_oficial_sem_bloquear_cadastro(self):
        resposta = self.client.get(
            reverse('insumos:consultar_ca_epi'),
            {'numero_ca': '12345'},
        )

        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertEqual(dados['status'], 'UNAVAILABLE')
        self.assertEqual(dados['source'], 'caepi-local')
        self.assertIn('caepi.trabalho.gov.br', dados['consulta_oficial_url'])
        self.assertIn('txtNumeroCA=12345', dados['consulta_oficial_url'])

    def test_endpoint_rejeita_ca_vazio(self):
        resposta = self.client.get(reverse('insumos:consultar_ca_epi'))

        self.assertEqual(resposta.status_code, 400)
        self.assertFalse(resposta.json()['ok'])

    def test_tela_de_catalogo_exibe_acao_de_verificacao(self):
        resposta = self.client.get(reverse('insumos:criar_item_insumo'))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Verificar CA')
        self.assertContains(resposta, reverse('insumos:consultar_ca_epi'))
        self.assertContains(resposta, "if (normalizado === 'VALIDO') return 'success'")
        self.assertContains(resposta, "return 'danger'")
