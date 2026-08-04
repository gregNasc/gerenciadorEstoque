from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from uuid import uuid4
from estoque.models import (Emprestimo, ItemEmprestimo,)
from .comunicado_service import ComunicadoService
from .notificacao_service import NotificacaoService

class EmprestimoService:

    @staticmethod
    @transaction.atomic
    def criar(
        base_origem, base_destino, user, motivo, data_prevista, equipamentos,
        codigo_rastreio_envio='',
    ):

        if base_origem.grupo_regional != base_destino.grupo_regional:
            raise ValidationError(
                'Bases devem pertencer ao mesmo grupo.'
            )

        emprestimo = Emprestimo.objects.create(

            protocolo=(
                f'EMP-'
                f'{timezone.now().strftime("%y%m%d%H%M%S")}'
                f'{uuid4().hex[:4].upper()}'
            ),
            regional_origem=base_origem,
            regional_destino=base_destino,
            solicitado_por=user,
            motivo=motivo,
            data_emprestimo=timezone.localdate(),
            data_prevista_devolucao=data_prevista,
            grupo=base_origem.grupo_regional,
            status='AGUARDANDO_RECEBIMENTO',
            codigo_rastreio_envio=(codigo_rastreio_envio or '').strip(),
        )

        for equipamento in equipamentos:

            if equipamento.status != 'ATIVO':

                raise ValidationError(
                    f'Equipamento {equipamento.id} indisponível.'
                )

            ItemEmprestimo.objects.create(
                emprestimo=emprestimo,
                equipamento=equipamento,
                quantidade=1,
                status='ENVIADO',
            )

            equipamento.status = 'EM_TRANSITO'
            equipamento.save()
        ComunicadoService.emp_item_reservado(
            emprestimo,
            user,
        )
        NotificacaoService.emprestimo_aguardando_recebimento(
            emprestimo
        )

        return emprestimo

    @staticmethod
    @transaction.atomic
    def adicionar_itens(emprestimo, equipamentos):

        for eq in equipamentos:

            # proteção contra duplicidade
            if ItemEmprestimo.objects.filter(
                emprestimo=emprestimo,
                equipamento=eq
            ).exists():
                continue

            # proteção contra reserva concorrente
            if eq.status != 'ATIVO':
                raise ValidationError(f"Equipamento {eq.id} não está disponível.")

            ItemEmprestimo.objects.create(
                emprestimo=emprestimo,
                equipamento=eq,
                status='RESERVADO'
            )

            eq.status = 'RESERVADO_TRANSFERENCIA'
            eq.save()

        emprestimo.status = Emprestimo.Status.AGUARDANDO_RECEBIMENTO
        emprestimo.save(update_fields=['status'])

        ComunicadoService.emp_item_reservado(emprestimo)

    @staticmethod
    @transaction.atomic
    def enviar(emprestimo):

        if not emprestimo.itens.exists():
            raise ValidationError("Sem itens para envio.")

        emprestimo.status = Emprestimo.Status.AGUARDANDO_RECEBIMENTO
        emprestimo.save(update_fields=['status'])

        for item in emprestimo.itens.all():
            item.status = 'ENVIADO'
            item.equipamento.status = 'EM_TRANSITO'
            item.equipamento.save()
            item.save()

        ComunicadoService.emp_enviado(emprestimo)

    @staticmethod
    @transaction.atomic
    def receber(emprestimo, itens_recebidos_ids, usuario,):

        for item in emprestimo.itens.all():

            if str(item.id) in itens_recebidos_ids:
                item.status = 'RECEBIDO'
                equipamento = item.equipamento
                equipamento.status = 'EMPRESTADO'
                equipamento.regional = (
                    emprestimo.regional_destino
                )
                equipamento.save()
                item.save()

        emprestimo.status = 'EMPRESTADO'
        emprestimo.confirmado_recebimento = True
        emprestimo.save()

        ComunicadoService.emp_recebido(
            emprestimo=emprestimo,
            usuario=usuario,
        )

        NotificacaoService.emprestimo_recebido(
            emprestimo
        )

    @staticmethod
    @transaction.atomic
    def devolver(emprestimo, itens_devolvidos_ids, usuario, codigo_rastreio_devolucao=''):

        for item in emprestimo.itens.all():

            if item.status != 'RECEBIDO':
                continue

            if str(item.id) in itens_devolvidos_ids:
                item.status = 'DEVOLVIDO'

            else:
                item.status = 'DIVERGENCIA'
                item.observacao = (
                    'Equipamento não devolvido '
                    'na conferência.'
                )

            item.save()
        emprestimo.status = (
            'AGUARDANDO_CONFIRMACAO_DEVOLUCAO'
        )
        emprestimo.codigo_rastreio_devolucao = (codigo_rastreio_devolucao or '').strip()
        emprestimo.save(update_fields=['status', 'codigo_rastreio_devolucao', 'atualizado_em'])
        ComunicadoService.emp_devolucao_pendente(
            emprestimo,
            usuario,
        )
        NotificacaoService.emprestimo_devolucao_pendente(
            emprestimo
        )

    @staticmethod
    @transaction.atomic
    def confirmar_devolucao(emprestimo, itens_confirmados_ids, usuario,):

        for item in emprestimo.itens.select_related(
                'equipamento'
        ):

            item_id = str(item.id)

            if item_id in itens_confirmados_ids:
                equipamento = item.equipamento
                equipamento.status = 'ATIVO'
                equipamento.regional = (
                    emprestimo.regional_origem
                )
                equipamento.save()
                item.status = 'DEVOLVIDO'

            elif item.status == 'RECEBIDO':
                item.status = 'DIVERGENCIA'

            item.save()

        possui_pendencias = (
            emprestimo.itens.filter(
                status__in=[
                    'RECEBIDO',
                    'DIVERGENCIA',
                ]
            ).exists()

        )

        if possui_pendencias:
            emprestimo.status = 'EMPRESTADO'
            emprestimo.confirmado_devolucao = False
            emprestimo.data_devolucao = None

        else:
            emprestimo.status = 'FINALIZADO'
            emprestimo.confirmado_devolucao = True
            emprestimo.data_devolucao = (
                timezone.localdate()
            )
            NotificacaoService.emprestimo_finalizado(
                emprestimo
            )
        emprestimo.save()
        if possui_pendencias:
            ComunicadoService.emp_divergencia(
                emprestimo,
                usuario,
            )
        else:
            ComunicadoService.emp_devolucao(
                emprestimo,
                usuario,
            )
