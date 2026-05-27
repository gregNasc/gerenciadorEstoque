from django.db import transaction
from django.utils.translation import gettext_lazy as _
from .models import (
    Transferencia,
    TransferenciaItem,
    Notificacao,
    Comunicado,
    Historico,
)

def criar_transferencia_da_alocacao(alocacao):

    transferencia = Transferencia.objects.create(
        alocacao=alocacao,
        solicitado_por=alocacao.item.solicitacao.criado_por,
        regional_origem=alocacao.regional_origem,
        regional_destino=alocacao.item.solicitacao.regional_solicitante,
        status='PENDENTE'
    )

    equipamentos = alocacao.equipamentos.all()

    for eq in equipamentos:

        TransferenciaItem.objects.create(
            transferencia=transferencia,
            equipamento=eq,
            status='SELECIONADO'
        )

        eq.status = 'RESERVADO_TRANSFERENCIA'

        eq.save()

    return transferencia

# NOTIFICAÇÕES
class NotificacaoService:

    @staticmethod
    def criar(
        usuario,
        tipo,
        evento,
        mensagem,
        transferencia=None,
        solicitacao=None,
        link=None,
    ):
        """
        Cria notificação evitando duplicidade.
        """

        notificacao, _ = Notificacao.objects.get_or_create(
            usuario=usuario,
            tipo=tipo,
            evento=evento,
            transferencia=transferencia,
            solicitacao=solicitacao,
            defaults={
                'mensagem': mensagem,
                'link': link,
            }
        )

        return notificacao

    @staticmethod
    def transferencia_criada(transferencia):
        """
        Notifica usuários da regional destino.
        """

        regional_destino = transferencia.regional_destino

        if not regional_destino:
            return

        usuarios = regional_destino.usuarios.all()

        for usuario in usuarios:

            NotificacaoService.criar(
                usuario=usuario,
                tipo='TRANSFERENCIA',
                evento='CRIADA',
                transferencia=transferencia,
                mensagem=_(
                    f'Nova transferência #{transferencia.id} criada.'
                ),
                link=f'/transferencias/{transferencia.id}/'
            )

    @staticmethod
    def transferencia_recebida(transferencia):
        """
        Notifica recebimento da transferência.
        """

        regional_origem = transferencia.regional_origem

        if not regional_origem:
            return

        usuarios = regional_origem.usuarios.all()

        for usuario in usuarios:

            NotificacaoService.criar(
                usuario=usuario,
                tipo='TRANSFERENCIA',
                evento='RECEBIDA',
                transferencia=transferencia,
                mensagem=_(
                    f'Transferência #{transferencia.id} foi recebida.'
                ),
                link=f'/transferencias/{transferencia.id}/'
            )

# HISTÓRICO
class HistoricoService:

    @staticmethod
    def registrar(
        acao,
        usuario=None,
        transferencia=None,
        dados=None,
    ):
        """
        Registra eventos no histórico.
        """

        Historico.objects.create(
            acao=acao,
            usuario=usuario,
            transferencia=transferencia,
            dados=dados or {}
        )

# COMUNICADOS
class ComunicadoService:

    @staticmethod
    def criar_operacional(
        titulo,
        mensagem,
        criado_por,
        empresa=None,
        usuarios=None,
    ):
        """
        Cria comunicado operacional.
        """

        comunicado = Comunicado.objects.create(
            titulo=titulo,
            mensagem=mensagem,
            tipo='OPERACIONAL',
            criado_por=criado_por,
            empresa=empresa,
        )

        if usuarios:
            comunicado.usuarios.set(usuarios)

        return comunicado

    @staticmethod
    def transferencia_criada(transferencia):
        """
        Comunicado automático para transferência criada.
        """

        ComunicadoService.criar_operacional(
            titulo=f'Transferência #{transferencia.id}',
            mensagem=(
                f'Nova transferência criada entre '
                f'{transferencia.regional_origem} '
                f'e {transferencia.regional_destino}.'
            ),
            criado_por=transferencia.solicitado_por,
            empresa=getattr(
                transferencia.regional_destino,
                'empresa',
                None
            )
        )

# TRANSFERÊNCIAS
class TransferenciaService:

    @staticmethod
    @transaction.atomic
    def criar_da_alocacao(alocacao):
        """
        Cria transferência baseada em alocação.
        """

        transferencia = Transferencia.objects.create(
            alocacao=alocacao,
            solicitado_por=alocacao.item.solicitacao.criado_por,
            regional_origem=alocacao.regional_origem,
            regional_destino=(
                alocacao.item.solicitacao.regional_solicitante
            ),
            status='PENDENTE'
        )

        equipamentos = (
            alocacao.equipamentos
            .select_related('produto')
            .all()
        )

        for eq in equipamentos:

            TransferenciaItem.objects.create(
                transferencia=transferencia,
                equipamento=eq,
                status='SELECIONADO'
            )

            eq.status = 'RESERVADO_TRANSFERENCIA'

            eq.save(
                update_fields=['status']
            )


        # HISTÓRICO
        HistoricoService.registrar(
            acao='TRANSFERENCIA_CRIADA',
            usuario=transferencia.solicitado_por,
            transferencia=transferencia,
            dados={
                'transferencia_id': transferencia.id,
                'regional_origem': str(
                    transferencia.regional_origem
                ),
                'regional_destino': str(
                    transferencia.regional_destino
                ),
            }
        )


        # NOTIFICAÇÕES
        NotificacaoService.transferencia_criada(
            transferencia
        )


        # COMUNICADOS
        ComunicadoService.transferencia_criada(
            transferencia
        )

        return transferencia

    @staticmethod
    @transaction.atomic
    def receber_transferencia(
        transferencia,
        usuario_recebimento,
    ):
        """
        Finaliza recebimento da transferência.
        """

        transferencia.status = 'RECEBIDA'

        transferencia.save(
            update_fields=['status']
        )

        itens = transferencia.itens.select_related(
            'equipamento'
        ).all()

        for item in itens:

            equipamento = item.equipamento

            equipamento.status = 'DISPONIVEL'

            equipamento.regional = (
                transferencia.regional_destino
            )

            equipamento.save(
                update_fields=[
                    'status',
                    'regional',
                ]
            )

            item.status = 'RECEBIDO'

            item.save(
                update_fields=['status']
            )


        # HISTÓRICO


        HistoricoService.registrar(
            acao='TRANSFERENCIA_RECEBIDA',
            usuario=usuario_recebimento,
            transferencia=transferencia,
            dados={
                'transferencia_id': transferencia.id,
            }
        )


        # NOTIFICAÇÕES


        NotificacaoService.transferencia_recebida(
            transferencia
        )

        return transferencia

# COMPATIBILIDADE LEGADA
def criar_transferencia_da_alocacao(alocacao):
    """
    Compatibilidade com código legado.
    """

    return TransferenciaService.criar_da_alocacao(
        alocacao
    )