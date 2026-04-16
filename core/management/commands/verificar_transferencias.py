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
            data_solicitacao__lt=limite
        )

        total = transferencias.count()

        for t in transferencias:
            t.status = 'CANCELADO'
            t.save()

            equipamento = t.equipamento
            equipamento.base = t.regional_origem
            equipamento.status = 'DISPONIVEL'
            equipamento.save()

        self.stdout.write(f"{total} transferências canceladas.")