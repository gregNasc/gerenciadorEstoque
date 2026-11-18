from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from estoque.models import Comunicado, ComunicadoEntrega
from estoque.services.comunicacoes.dispatcher import ComunicacaoDispatcher
from estoque.services.comunicacoes.outbox_service import OutboxService


class Command(BaseCommand):
    help = (
        'Consulta o comunicado mais recente e, com --enviar, cria e processa '
        'somente as entregas de e-mail desse comunicado.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--enviar',
            action='store_true',
            help='Cria as entregas ausentes e processa somente o último comunicado.',
        )

    @staticmethod
    def _resumo(comunicado):
        entregas = comunicado.entregas.filter(
            canal=ComunicadoEntrega.Canal.EMAIL,
        )
        return Counter(entregas.values_list('status', flat=True))

    def handle(self, *args, **options):
        comunicado = Comunicado.objects.order_by('-criado_em', '-pk').first()
        if comunicado is None:
            raise CommandError('Nenhum comunicado foi encontrado.')

        self.stdout.write(
            f'Último comunicado: #{comunicado.pk} — {comunicado.titulo}'
        )
        self.stdout.write(
            f'Destinatários internos: {comunicado.usuarios.filter(is_active=True).count()}'
        )
        self.stdout.write(f'Entregas de e-mail atuais: {dict(self._resumo(comunicado))}')

        if not options['enviar']:
            self.stdout.write(
                'Consulta concluída. Use --enviar para criar entregas ausentes '
                'e processar somente este comunicado.'
            )
            return

        ComunicacaoDispatcher.criar_entregas(comunicado.pk)
        processadas = OutboxService.processar(
            canal=ComunicadoEntrega.Canal.EMAIL,
            limit=max(1, comunicado.usuarios.filter(is_active=True).count()),
            comunicado_id=comunicado.pk,
        )
        comunicado.refresh_from_db()
        self.stdout.write(f'Entregas processadas agora: {len(processadas)}')
        self.stdout.write(f'Situação final: {dict(self._resumo(comunicado))}')
        self.stdout.write(self.style.SUCCESS('Processamento do último comunicado concluído.'))
