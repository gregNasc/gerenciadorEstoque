import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from estoque.models import ComunicadoEntrega


class OperacaoComunicacoesTests(TestCase):
    @override_settings(
        WHATSAPP_ACCESS_TOKEN='token-nao-pode-aparecer',
        WHATSAPP_API_BASE_URL='https://graph.example.com',
        WHATSAPP_PHONE_NUMBER_ID='numero-1',
        WHATSAPP_WEBHOOK_VERIFY_TOKEN='verify-nao-pode-aparecer',
        WHATSAPP_WEBHOOK_APP_SECRET='secret-nao-pode-aparecer',
    )
    def test_diagnostico_json_informa_presenca_sem_revelar_segredos(self):
        saida = StringIO()

        call_command('diagnosticar_comunicacoes', '--json', stdout=saida)

        texto = saida.getvalue()
        dados = json.loads(texto)
        self.assertTrue(
            dados['whatsapp']['configuracao']['WHATSAPP_ACCESS_TOKEN']
        )
        self.assertNotIn('token-nao-pode-aparecer', texto)
        self.assertNotIn('verify-nao-pode-aparecer', texto)
        self.assertNotIn('secret-nao-pode-aparecer', texto)

    @patch(
        'estoque.management.commands.executar_worker_comunicacoes.OutboxService.processar'
    )
    def test_worker_um_ciclo_processa_email_e_whatsapp(self, processar):
        processar.side_effect = [[], []]

        call_command(
            'executar_worker_comunicacoes',
            max_ciclos=1,
            intervalo=5,
            stdout=StringIO(),
        )

        self.assertEqual(processar.call_count, 2)
        self.assertEqual(
            [chamada.kwargs['canal'] for chamada in processar.call_args_list],
            [ComunicadoEntrega.Canal.EMAIL, ComunicadoEntrega.Canal.WHATSAPP],
        )
