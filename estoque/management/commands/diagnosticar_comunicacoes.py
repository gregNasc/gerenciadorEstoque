import json

from django.conf import settings
from django.core.management.base import BaseCommand

from estoque.checks import comunicacoes_externas_configuradas
from estoque.models import ComunicadoEntrega, Perfil
from estoque.services.comunicacoes.templates import REGISTRO_TEMPLATES


class Command(BaseCommand):
    help = 'Exibe a prontidão de e-mail/WhatsApp sem revelar credenciais.'

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', dest='como_json')

    @staticmethod
    def _configurado(valor):
        return bool(str(valor or '').strip())

    def _dados(self):
        email_campos = {
            'EMAIL_HOST': settings.EMAIL_HOST,
            'EMAIL_HOST_USER': settings.EMAIL_HOST_USER,
            'EMAIL_HOST_PASSWORD': settings.EMAIL_HOST_PASSWORD,
            'DEFAULT_FROM_EMAIL': settings.DEFAULT_FROM_EMAIL,
        }
        whatsapp_campos = {
            'WHATSAPP_API_BASE_URL': settings.WHATSAPP_API_BASE_URL,
            'WHATSAPP_ACCESS_TOKEN': settings.WHATSAPP_ACCESS_TOKEN,
            'WHATSAPP_PHONE_NUMBER_ID': settings.WHATSAPP_PHONE_NUMBER_ID,
            'WHATSAPP_WEBHOOK_VERIFY_TOKEN': settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN,
            'WHATSAPP_WEBHOOK_APP_SECRET': settings.WHATSAPP_WEBHOOK_APP_SECRET,
        }

        def filas(canal):
            base = ComunicadoEntrega.objects.filter(canal=canal)
            return {
                'pendentes': base.filter(status='PENDENTE').count(),
                'processando': base.filter(status='PROCESSANDO').count(),
                'falhas': base.filter(status='FALHA').count(),
            }

        erros = comunicacoes_externas_configuradas(None)
        return {
            'email': {
                'habilitado': settings.NOTIFICACOES_EMAIL_ENABLED,
                'backend': settings.EMAIL_BACKEND,
                'configuracao': {
                    nome: self._configurado(valor)
                    for nome, valor in email_campos.items()
                },
                'fila': filas(ComunicadoEntrega.Canal.EMAIL),
            },
            'whatsapp': {
                'habilitado': settings.WHATSAPP_ENABLED,
                'provedor': settings.WHATSAPP_PROVIDER,
                'configuracao': {
                    nome: self._configurado(valor)
                    for nome, valor in whatsapp_campos.items()
                },
                'usuarios_com_consentimento': Perfil.objects.filter(
                    user__is_active=True,
                    whatsapp_ativo=True,
                    whatsapp_consentimento_em__isnull=False,
                    whatsapp_revogado_em__isnull=True,
                ).count(),
                'templates_cadastrados': sorted(REGISTRO_TEMPLATES),
                'fila': filas(ComunicadoEntrega.Canal.WHATSAPP),
            },
            'checks': [
                {'id': erro.id, 'mensagem': erro.msg, 'orientacao': erro.hint or ''}
                for erro in erros
            ],
        }

    def handle(self, *args, **options):
        dados = self._dados()
        if options['como_json']:
            self.stdout.write(json.dumps(dados, ensure_ascii=False, indent=2))
            return

        for canal in ('email', 'whatsapp'):
            item = dados[canal]
            self.stdout.write(self.style.MIGRATE_HEADING(canal.upper()))
            self.stdout.write(
                f"Habilitado: {'sim' if item['habilitado'] else 'não'}"
            )
            for nome, configurado in item['configuracao'].items():
                self.stdout.write(
                    f"- {nome}: {'configurado' if configurado else 'ausente'}"
                )
            fila = item['fila']
            self.stdout.write(
                'Fila: '
                f"{fila['pendentes']} pendente(s), "
                f"{fila['processando']} processando, "
                f"{fila['falhas']} falha(s)."
            )
        if dados['checks']:
            self.stdout.write(self.style.WARNING(
                'Há configurações obrigatórias ausentes para canais habilitados.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                'Configuração coerente com as flags atuais.'
            ))
