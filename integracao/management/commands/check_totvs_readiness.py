from django.core.management.base import BaseCommand, CommandError

from integracao.models import TotvsIntegrationConfig
from integracao.totvs.readiness import TotvsReadinessService


class Command(BaseCommand):
    help = 'Verifica a preparação da integração TOTVS sem acessar serviços externos.'

    def add_arguments(self, parser):
        parser.add_argument('--empresa-id', type=int)
        parser.add_argument('--fail-on-blocker', action='store_true')

    def handle(self, *args, **options):
        configs = TotvsIntegrationConfig.objects.select_related('empresa').order_by('empresa__nome')
        if options['empresa_id']:
            configs = configs.filter(empresa_id=options['empresa_id'])
        if not configs.exists():
            message = 'Nenhuma empresa possui configuração TOTVS.'
            if options['fail_on_blocker']:
                raise CommandError(message)
            self.stdout.write(self.style.WARNING(message))
            return

        blocked = 0
        for config in configs:
            result = TotvsReadinessService.avaliar(config)
            if result.pronto:
                self.stdout.write(self.style.SUCCESS(f'{config.empresa}: pronta para homologação.'))
                continue
            blocked += 1
            self.stdout.write(self.style.WARNING(f'{config.empresa}: bloqueada.'))
            for reason in result.bloqueios:
                self.stdout.write(f'  - {reason}')
        if blocked and options['fail_on_blocker']:
            raise CommandError(f'{blocked} configuração(ões) possuem bloqueios.')
