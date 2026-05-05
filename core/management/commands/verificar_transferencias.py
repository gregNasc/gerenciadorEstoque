from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from estoque.models import Transferencia

class Command(BaseCommand):
    help = 'Cancela transferências antigas automaticamente'

    def handle(self, *args, **kwargs):
        limite = timezone.now() - timedelta(days=3)

        transferencias = Transferencia.objects.filter(
            status='PENDENTE',
            data_envio__lt=limite
        )

        total = transferencias.count()

        for t in transferencias:
            t.status = 'CANCELADO'
            t.save(update_fields=['status'])

            for item in t.itens.all():
                for eq in item.equipamentos.all():
                    eq.status = 'ATIVO'
                    eq.save(update_fields=['status'])

        self.stdout.write(f"{total} transferências canceladas.")