from django.contrib.auth.models import User
from django.db.models import Q
from estoque.models import Notificacao

class NotificacaoService:

    @staticmethod
    def criar(usuario, tipo, evento, mensagem, transferencia=None, solicitacao=None, link=None,):
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

    @staticmethod
    def emprestimo_aguardando_recebimento(emprestimo):

        usuarios = User.objects.filter(
            perfil__regionais=
            emprestimo.regional_destino
        ).distinct()

        for usuario in usuarios:
            NotificacaoService.criar(
                usuario=usuario,
                tipo='EMPRESTIMO',
                evento='AGUARDANDO_RECEBIMENTO',
                mensagem=(
                    f'O empréstimo '
                    f'{emprestimo.protocolo} '
                    f'aguarda recebimento.'
                ),

                link=(
                    f'/emprestimos/'
                    f'{emprestimo.id}/'
                )
            )

    @staticmethod
    def emprestimo_recebido(emprestimo):

        usuarios = User.objects.filter(
            perfil__regionais=
            emprestimo.regional_origem
        ).distinct()

        for usuario in usuarios:
            NotificacaoService.criar(
                usuario=usuario,
                tipo='EMPRESTIMO',
                evento='RECEBIDO',
                mensagem=(
                    f'O empréstimo '
                    f'{emprestimo.protocolo} '
                    f'foi recebido.'
                ),
                link=(
                    f'/emprestimos/'
                    f'{emprestimo.id}/'
                )
            )

    @staticmethod
    def emprestimo_devolucao_pendente(emprestimo):

        usuarios = User.objects.filter(
            perfil__regionais=
            emprestimo.regional_origem
        ).distinct()

        for usuario in usuarios:
            NotificacaoService.criar(
                usuario=usuario,
                tipo='EMPRESTIMO',
                evento='DEVOLUCAO_PENDENTE',
                mensagem=(
                    f'O empréstimo '
                    f'{emprestimo.protocolo} '
                    f'aguarda confirmação '
                    f'de devolução.'
                ),
                link=(
                    f'/emprestimos/'
                    f'{emprestimo.id}/'
                )
            )

    @staticmethod
    def emprestimo_finalizado(emprestimo):

        usuarios = User.objects.filter(

            Q(
                perfil__regionais=
                emprestimo.regional_origem
            ) |
            Q(
                perfil__regionais=
                emprestimo.regional_destino
            )

        ).distinct()

        for usuario in usuarios:
            NotificacaoService.criar(
                usuario=usuario,
                tipo='EMPRESTIMO',
                evento='FINALIZADO',
                mensagem=(
                    f'O empréstimo '
                    f'{emprestimo.protocolo} '
                    f'foi finalizado.'
                ),
                link=(
                    f'/emprestimos/'
                    f'{emprestimo.id}/'
                )
            )