from django.core.management.base import BaseCommand
from estoque.models import Produto, Sick, HistoricoTransferencia
from django.utils.timezone import localtime

class Command(BaseCommand):
    help = "Verifica os dados migrados do sistema de estoque"

    def handle(self, *args, **options):
        self.stdout.write("=== PRODUTOS ===")
        for p in Produto.objects.all():
            self.stdout.write(f"{p.id} | {p.descricao} | {p.codigo} | {p.quantidade} | {p.regional}")

        self.stdout.write("\n=== EQUIPAMENTOS EM SICK ===")
        for s in Sick.objects.all():
            data = localtime(s.data_ocorrencia).strftime("%d/%m/%Y %H:%M")
            self.stdout.write(f"{s.id} | {s.codigo} | {s.descricao} | {s.regional} | {s.motivo} | {data}")

        self.stdout.write("\n=== HISTÓRICO DE TRANSFERÊNCIAS ===")
        for h in HistoricoTransferencia.objects.all():
            data = localtime(h.data_movimentacao).strftime("%d/%m/%Y %H:%M")
            self.stdout.write(f"{h.id} | {h.codigo} | {h.descricao} | {h.quantidade} | {h.regional_origem} -> {h.regional_destino} | {data}")

        self.stdout.write("\n=== RESUMO ===")
        self.stdout.write(f"Total de produtos: {Produto.objects.count()}")
        self.stdout.write(f"Total de equipamentos em Sick: {Sick.objects.count()}")
        self.stdout.write(f"Total de transferências: {HistoricoTransferencia.objects.count()}")
