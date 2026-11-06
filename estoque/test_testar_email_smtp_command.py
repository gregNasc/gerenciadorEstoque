from io import StringIO
import smtplib
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, override_settings


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    EMAIL_HOST='smtp.example.com',
    EMAIL_HOST_USER='sistema@example.com',
    EMAIL_HOST_PASSWORD='senha-de-aplicativo',
    DEFAULT_FROM_EMAIL='sistema@example.com',
)
class TestarEmailSmtpCommandTests(SimpleTestCase):
    def test_sem_confirmacao_apenas_valida(self):
        stdout = StringIO()
        call_command(
            'testar_email_smtp', destino='destino@example.com', stdout=stdout,
        )
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn('Nenhuma mensagem foi enviada', stdout.getvalue())
        self.assertNotIn('destino@example.com', stdout.getvalue())

    def test_com_confirmacao_envia_um_email(self):
        call_command(
            'testar_email_smtp', destino='destino@example.com', enviar=True,
            stdout=StringIO(),
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['destino@example.com'])

    @patch(
        'django.core.mail.message.EmailMessage.send',
        side_effect=smtplib.SMTPServerDisconnected('conexão encerrada'),
    )
    def test_falha_de_login_exibe_orientacao_sem_traceback(self, _send):
        with self.assertRaisesMessage(CommandError, 'senha de app de 16 dígitos'):
            call_command(
                'testar_email_smtp', destino='destino@example.com', enviar=True,
                stdout=StringIO(),
            )
