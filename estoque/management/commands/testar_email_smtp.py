import smtplib

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.core.exceptions import ValidationError


class Command(BaseCommand):
    help = 'Valida a configuração SMTP e, mediante confirmação, envia um teste.'

    def add_arguments(self, parser):
        parser.add_argument('--destino', required=True)
        parser.add_argument(
            '--enviar',
            action='store_true',
            help='Envia o e-mail. Sem esta opção, apenas valida a configuração.',
        )

    def handle(self, *args, **options):
        destino = options['destino'].strip()
        try:
            validate_email(destino)
        except ValidationError as exc:
            raise CommandError('O endereço informado em --destino é inválido.') from exc

        obrigatorias = {
            'EMAIL_HOST': settings.EMAIL_HOST,
            'EMAIL_HOST_USER': settings.EMAIL_HOST_USER,
            'EMAIL_HOST_PASSWORD': settings.EMAIL_HOST_PASSWORD,
            'DEFAULT_FROM_EMAIL': settings.DEFAULT_FROM_EMAIL,
        }
        ausentes = [
            nome for nome, valor in obrigatorias.items()
            if not str(valor or '').strip()
        ]
        if ausentes:
            raise CommandError(
                'Configuração incompleta: ' + ', '.join(ausentes) + '.',
            )

        destino_mascarado = self._mascarar(destino)
        self.stdout.write(self.style.SUCCESS(
            f'Configuração SMTP preenchida. Destino de teste: {destino_mascarado}',
        ))
        if not options['enviar']:
            self.stdout.write(
                'Nenhuma mensagem foi enviada. Acrescente --enviar para confirmar o teste.',
            )
            return

        mensagem = EmailMultiAlternatives(
            subject='Teste de e-mail — Gestor de Inventário',
            body=(
                'Este é um teste da configuração de e-mail do Gestor de Inventário. '
                'Nenhuma ação é necessária.'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[destino],
        )
        try:
            enviados = mensagem.send()
        except smtplib.SMTPAuthenticationError as exc:
            raise CommandError(
                'O servidor SMTP recusou a autenticação. Para Gmail, use uma '
                'senha de app de 16 dígitos em EMAIL_HOST_PASSWORD; não use a '
                'senha comum da conta.',
            ) from exc
        except smtplib.SMTPServerDisconnected as exc:
            raise CommandError(
                'O servidor SMTP encerrou a conexão durante o login. Confirme '
                'host, porta e TLS. Para Gmail, substitua a senha comum por uma '
                'senha de app de 16 dígitos.',
            ) from exc
        except (smtplib.SMTPConnectError, TimeoutError, OSError) as exc:
            raise CommandError(
                'Não foi possível concluir a conexão SMTP. Confira host, porta, '
                'TLS, firewall e a disponibilidade do provedor.',
            ) from exc
        if enviados != 1:
            raise CommandError('O provedor não confirmou o envio do e-mail de teste.')
        self.stdout.write(self.style.SUCCESS('E-mail de teste enviado com sucesso.'))

    @staticmethod
    def _mascarar(endereco):
        local, dominio = endereco.rsplit('@', 1)
        local_visivel = local[:2] if len(local) > 2 else local[:1]
        return f'{local_visivel}{"*" * max(3, len(local) - len(local_visivel))}@{dominio}'
