from unittest.mock import patch

from django.db import OperationalError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse


class HealthLiveTests(SimpleTestCase):
    def test_live_nao_depende_do_banco(self):
        response = self.client.get(reverse('health_live'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})
        self.assertIn('no-cache', response.headers['Cache-Control'])

    def test_live_aceita_apenas_get(self):
        self.assertEqual(self.client.post(reverse('health_live')).status_code, 405)


class HealthReadyTests(TestCase):
    def test_ready_valida_banco(self):
        response = self.client.get(reverse('health_ready'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    @patch('core.health.connections')
    def test_ready_retorna_503_sem_expor_erro(self, connections):
        connections.__getitem__.side_effect = OperationalError('credencial-secreta')

        response = self.client.get(reverse('health_ready'))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'status': 'unavailable'})
        self.assertNotContains(response, 'credencial-secreta', status_code=503)
