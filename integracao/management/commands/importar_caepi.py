from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from integracao.services.caepi_import_service import CaepiImportService


class Command(BaseCommand):
    help = 'Prepara e opcionalmente publica uma versão local da base oficial CAEPI.'

    def add_arguments(self, parser):
        parser.add_argument('arquivo')
        parser.add_argument('--usuario', required=True)
        parser.add_argument('--publicar', action='store_true')

    def handle(self, *args, **options):
        path = Path(options['arquivo']).resolve()
        if not path.is_file():
            raise CommandError(f'Arquivo não encontrado: {path}')
        user = get_user_model().objects.filter(
            username=options['usuario'], is_superuser=True, is_active=True,
        ).first()
        if user is None:
            raise CommandError('Informe um Superuser ativo em --usuario.')
        with path.open('rb') as stream:
            importacao = CaepiImportService.preparar_previa(
                uploaded_file=File(stream, name=path.name), user=user,
            )
        self.stdout.write(
            f'Prévia #{importacao.pk}: {importacao.total_registros} registros; '
            f'{importacao.rejeitados} rejeitados; status={importacao.status}.'
        )
        if options['publicar'] and importacao.status != importacao.Status.PUBLICADA:
            importacao = CaepiImportService.publicar(importacao.pk)
            self.stdout.write(self.style.SUCCESS(
                f'Base CAEPI publicada: importação #{importacao.pk}.',
            ))
