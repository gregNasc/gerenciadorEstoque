from django.db import transaction
from django.utils.translation import gettext_lazy as _
from .models import (Transferencia, TransferenciaItem, Notificacao, Comunicado, Historico,)
from .models import (Emprestimo, ItemEmprestimo)
from estoque.services import NotificacaoService
from django.contrib.auth.models import User

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

#EMPRÉSTIMOS
class EmprestimoService:

    @staticmethod
    @transaction.atomic
    def criar(base_origem, base_destino, user, motivo, data_prevista, equipamentos):

        if base_origem.grupo_regional != base_destino.grupo_regional:
            raise ValidationError(
                'Bases devem pertencer ao mesmo grupo.'
            )

        emprestimo = Emprestimo.objects.create(

            protocolo=(
                f'EMP-'
                f'{timezone.now().strftime("%Y%m%d%H%M%S")}'
            ),
            regional_origem=base_origem,
            regional_destino=base_destino,
            solicitado_por=user,
            motivo=motivo,
            data_emprestimo=timezone.localdate(),
            data_prevista_devolucao=data_prevista,
            grupo=base_origem.grupo_regional,
            status='AGUARDANDO_RECEBIMENTO',
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
            emprestimo
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

        emprestimo.status = 'RESERVADO'
        emprestimo.save()

        ComunicadoService.emp_item_reservado(emprestimo)

    @staticmethod
    @transaction.atomic
    def enviar(emprestimo):

        if not emprestimo.itens.exists():
            raise ValidationError("Sem itens para envio.")

        emprestimo.status = 'EM_TRANSITO'
        emprestimo.save()

        for item in emprestimo.itens.all():
            item.status = 'ENVIADO'
            item.equipamento.status = 'EM_TRANSITO'
            item.equipamento.save()
            item.save()

        ComunicadoService.emp_enviado(emprestimo)

    @staticmethod
    @transaction.atomic
    def receber(emprestimo, itens_recebidos_ids):

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

        NotificacaoService.emprestimo_recebido(
            emprestimo
        )

    @staticmethod
    @transaction.atomic
    def devolver(emprestimo, itens_devolvidos_ids):

        for item in emprestimo.itens.all():

            if str(item.id) in itens_devolvidos_ids:
                item.status = 'DEVOLVIDO'

                item.save()

        emprestimo.status = (
            'AGUARDANDO_CONFIRMACAO_DEVOLUCAO'
        )

        emprestimo.save()

        NotificacaoService.emprestimo_devolucao_pendente(
            emprestimo
        )

    @staticmethod
    @transaction.atomic
    def confirmar_devolucao(emprestimo, itens_confirmados_ids):

        for item in emprestimo.itens.all():

            if str(item.id) in itens_confirmados_ids:
                item.status = 'DEVOLVIDO'
                equipamento = item.equipamento
                equipamento.status = 'ATIVO'
                equipamento.regional = (
                    emprestimo.regional_origem
                )
                equipamento.save()
                item.save()

        emprestimo.status = 'FINALIZADO'
        emprestimo.confirmado_devolucao = True
        emprestimo.data_devolucao = (
            timezone.localdate()
        )
        emprestimo.save()
        ComunicadoService.emp_devolucao(
            emprestimo
        )
        NotificacaoService.emprestimo_finalizado(
            emprestimo
        )

class ComunicadoService:

    @staticmethod
    def emp_item_reservado(emp):
        Comunicado.objects.create(
            titulo="Empréstimo iniciado",
            mensagem=f"{emp.regional_origem.nome} reservou equipamentos para {emp.regional_destino.nome}.",
            tipo="EMPRESTIMO"
        )

    @staticmethod
    def emp_enviado(emp):
        Comunicado.objects.create(
            titulo="Equipamentos enviados",
            mensagem=f"Equipamentos enviados de {emp.regional_origem.nome} para {emp.regional_destino.nome}.",
            tipo="EMPRESTIMO"
        )

    @staticmethod
    def emp_divergencia(emp):
        Comunicado.objects.create(
            titulo="Divergência no empréstimo",
            mensagem=f"Divergência detectada no empréstimo {emp.protocolo}.",
            tipo="ALERTA"
        )

    @staticmethod
    def emp_devolucao(emp):
        Comunicado.objects.create(
            titulo="Empréstimo finalizado",
            mensagem=f"Devolução concluída entre {emp.regional_origem.nome} e {emp.regional_destino.nome}.",
            tipo="EMPRESTIMO"
        )