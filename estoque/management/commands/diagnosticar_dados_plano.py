import json

from django.core.management.base import BaseCommand
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Lower, Trim

from estoque.models import Base, Empresa, Equipamento, Perfil, Produto, Transferencia
from insumos.models import FornecedorInsumo, Insumo, MovimentacaoInsumo


class Command(BaseCommand):
    help = 'Produz diagnóstico somente leitura antes das migrations do Plano Mestre.'

    def handle(self, *args, **options):
        duplicados_produto = list(
            Produto.objects.annotate(chave=Lower(Trim('descricao')))
            .values('chave')
            .annotate(total=Count('id'))
            .filter(total__gt=1)
            .order_by('-total', 'chave')[:100]
        )
        duplicados_insumo = list(
            Insumo.objects.annotate(chave=Lower(Trim('descricao')))
            .values('chave')
            .annotate(total=Count('id'))
            .filter(total__gt=1)
            .order_by('-total', 'chave')[:100]
        )
        movimentos_por_tipo = {
            item['tipo']: item['total']
            for item in MovimentacaoInsumo.objects.values('tipo')
            .annotate(total=Count('id'))
            .order_by('tipo')
        }
        quantidades_por_tipo = {
            item['tipo']: str(item['quantidade'] or 0)
            for item in MovimentacaoInsumo.objects.values('tipo')
            .annotate(quantidade=Sum('quantidade'))
            .order_by('tipo')
        }
        status_transferencia = {
            item['status']: item['total']
            for item in Transferencia.objects.values('status')
            .annotate(total=Count('id'))
            .order_by('status')
        }
        status_equipamento = {
            item['status']: item['total']
            for item in Equipamento.objects.values('status')
            .annotate(total=Count('id'))
            .order_by('status')
        }
        perfis_com_base_de_outra_empresa = Perfil.objects.filter(
            empresa_id__isnull=False,
        ).exclude(regionais__empresa_id=F('empresa_id')).filter(regionais__isnull=False).distinct().count()

        diagnostico = {
            'volumes': {
                'empresas': Empresa.objects.count(),
                'bases': Base.objects.count(),
                'produtos': Produto.objects.count(),
                'equipamentos': Equipamento.objects.count(),
                'insumos': Insumo.objects.count(),
                'fornecedores': FornecedorInsumo.objects.count(),
                'movimentacoes_insumo': MovimentacaoInsumo.objects.count(),
                'transferencias': Transferencia.objects.count(),
            },
            'nulos_ou_vazios': {
                'equipamentos_sem_produto': Equipamento.objects.filter(produto__isnull=True).count(),
                'equipamentos_sem_serie': Equipamento.objects.filter(Q(numero_serie='') | Q(numero_serie__isnull=True)).count(),
                'equipamentos_sem_patrimonio': Equipamento.objects.filter(Q(patrimonio='') | Q(patrimonio__isnull=True)).count(),
                'produtos_sem_descricao': Produto.objects.filter(descricao='').count(),
                'fornecedores_sem_documento': FornecedorInsumo.objects.filter(documento='').count(),
                'perfis_sem_empresa_nao_admin': Perfil.objects.filter(empresa__isnull=True).exclude(role=Perfil.Role.ADMIN).count(),
            },
            'duplicidades_normalizadas': {
                'produtos_descricao': duplicados_produto,
                'insumos_descricao': duplicados_insumo,
            },
            'fora_do_dominio': {
                'movimentos_quantidade_nao_positiva': MovimentacaoInsumo.objects.filter(quantidade__lte=0).count(),
                'movimentos_valor_negativo': MovimentacaoInsumo.objects.filter(valor_unitario__lt=0).count(),
                'insumos_minimo_negativo': Insumo.objects.filter(estoque_minimo__lt=0).count(),
                'insumos_maximo_menor_minimo': Insumo.objects.filter(estoque_maximo__lt=F('estoque_minimo')).count(),
                'perfis_com_base_de_outra_empresa': perfis_com_base_de_outra_empresa,
            },
            'distribuicoes': {
                'equipamentos_por_status': status_equipamento,
                'transferencias_por_status': status_transferencia,
                'movimentos_por_tipo': movimentos_por_tipo,
                'quantidades_movimentadas_por_tipo': quantidades_por_tipo,
            },
        }
        self.stdout.write(json.dumps(diagnostico, ensure_ascii=False, indent=2, default=str))
