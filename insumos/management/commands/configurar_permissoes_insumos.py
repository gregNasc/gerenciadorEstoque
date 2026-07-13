from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from insumos.constants import GruposInsumos
from insumos.permissions import Perms

class Command(BaseCommand):

    help = 'Configura grupos e permissões do módulo de insumos'

    def handle(self, *args, **kwargs):

        permissoes = Permission.objects.filter(
            content_type__app_label='insumos'
        )
        grupos = {
            GruposInsumos.SOLICITANTE: [
                'add_solicitacaoinsumo',
                'change_solicitacaoinsumo',
                'view_solicitacaoinsumo',
                'view_itemsolicitacaoinsumo',
                'view_inventario',
                'view_checklistdiario',
                'view_itemchecklist',
            ],

            GruposInsumos.COMPRAS: [
                'view_solicitacaoinsumo',
                'aprovar_solicitacao',
                'reprovar_solicitacao',
                'colocar_em_compra',
                'finalizar_solicitacao',
                'view_movimentacaoinsumo',
                'realizar_entrada',
                'realizar_saida',
                'realizar_devolucao',
                'realizar_perda',
                'realizar_ajuste',
                'view_consumoinsumo',
                'visualizar_custos',
                'visualizar_dashboards_financeiros',
                'view_fornecedorinsumo',
                'add_fornecedorinsumo',
                'change_fornecedorinsumo',
                'view_precofornecedorinsumo',
                'add_precofornecedorinsumo',
                'change_precofornecedorinsumo',
            ],

            GruposInsumos.PLANEJAMENTO: [
                'view_inventario',
                'add_inventario',
                'change_inventario',
                'gerenciar_inventarios',
                'view_checklistdiario',
                'add_checklistdiario',
                'change_checklistdiario',
                'gerenciar_checklists',
                'finalizar_checklists',
                'view_consumoinsumo',
                'view_movimentacaoinsumo',
                'view_movimentacaotag',
                'view_lotetag',
                'gerenciar_tags',
            ],

            GruposInsumos.FINANCEIRO: [
                'view_consumoinsumo',
                'view_movimentacaoinsumo',
                'visualizar_custos',
                'visualizar_dashboards_financeiros',
                'view_fornecedorinsumo',
                'view_precofornecedorinsumo',
            ],

            GruposInsumos.EXECUTIVO: list(
                permissoes.values_list(
                    'codename',
                    flat=True
                )
            ),
        }

        for nome_grupo, codenames in grupos.items():
            grupo, _ = Group.objects.get_or_create(
                name=nome_grupo
            )
            grupo.permissions.clear()
            perms = Permission.objects.filter(
                content_type__app_label='insumos',
                codename__in=codenames
            )
            grupo.permissions.add(*perms)
            self.stdout.write(
                self.style.SUCCESS(
                    f'Grupo {nome_grupo} configurado.'
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                'Permissões do módulo de insumos configuradas com sucesso.'
            )
        )
