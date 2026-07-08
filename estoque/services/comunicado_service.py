from datetime import timedelta

from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone

from estoque.models import Base, Comunicado


class ComunicadoService:
    DIAS_EXPIRACAO_PADRAO = 30

    @staticmethod
    def expira_em_padrao():
        return timezone.now() + timedelta(days=ComunicadoService.DIAS_EXPIRACAO_PADRAO)

    @staticmethod
    def usuarios_por_bases(bases, incluir_admins=True, excluir_usuario=None):
        bases_ids = []

        if bases is None:
            bases_ids = []
        elif hasattr(bases, 'values_list'):
            bases_ids = list(bases.values_list('id', flat=True))
        else:
            for base in bases:
                if isinstance(base, Base):
                    bases_ids.append(base.id)
                elif base:
                    bases_ids.append(base)

        filtros = Q()
        if bases_ids:
            filtros |= Q(perfil__regionais__id__in=bases_ids)

        if incluir_admins:
            filtros |= Q(perfil__role='admin')

        usuarios = User.objects.filter(is_active=True)
        if filtros:
            usuarios = usuarios.filter(filtros)

        if excluir_usuario:
            usuarios = usuarios.exclude(id=excluir_usuario.id)

        return usuarios.distinct()

    @staticmethod
    def criar_acao(
        *,
        titulo,
        mensagem,
        usuario,
        tipo='OPERACIONAL',
        usuarios=None,
        bases=None,
        empresa=None,
        enviar_para_todos=False,
        permitir_limpar=True,
        expira_em=None,
        incluir_admins=True,
    ):
        if usuario is None:
            usuario = User.objects.filter(is_active=True, is_superuser=True).first()
        if usuario is None:
            usuario = User.objects.filter(is_active=True).first()
        if usuario is None:
            return None

        comunicado = Comunicado.objects.create(
            titulo=titulo,
            mensagem=mensagem,
            tipo=tipo,
            criado_por=usuario,
            empresa=empresa,
            enviar_para_todos=enviar_para_todos,
            permitir_limpar=permitir_limpar,
            expira_em=expira_em or ComunicadoService.expira_em_padrao(),
        )

        if enviar_para_todos:
            destinatarios = User.objects.filter(is_active=True)
            if empresa:
                destinatarios = destinatarios.filter(perfil__empresa=empresa)
            comunicado.usuarios.set(destinatarios.distinct())
        elif usuarios is not None:
            comunicado.usuarios.set(usuarios)
        elif bases is not None:
            comunicado.usuarios.set(
                ComunicadoService.usuarios_por_bases(
                    bases,
                    incluir_admins=incluir_admins,
                    excluir_usuario=usuario,
                )
            )

        return comunicado

    @staticmethod
    def excluir_expirados():
        return Comunicado.objects.filter(
            expira_em__isnull=False,
            expira_em__lte=timezone.now(),
        ).delete()

    @staticmethod
    def checklist_criado(checklist, usuario):
        return ComunicadoService.criar_acao(
            titulo=f'Checklist #{checklist.id} criado',
            mensagem=(
                f'Checklist #{checklist.id} criado para '
                f'{checklist.inventario.cliente.sigla} - Loja {checklist.inventario.loja}.\n\n'
                f'Base: {checklist.inventario.base.nome}\n'
                f'Responsavel: {checklist.responsavel.get_username()}'
            ),
            usuario=usuario,
            tipo='OPERACIONAL',
            bases=[checklist.inventario.base],
            empresa=checklist.inventario.base.empresa,
        )

    @staticmethod
    def checklist_finalizado(checklist, usuario):
        return ComunicadoService.criar_acao(
            titulo=f'Checklist #{checklist.id} finalizado',
            mensagem=(
                f'Checklist #{checklist.id} finalizado para '
                f'{checklist.inventario.cliente.sigla} - Loja {checklist.inventario.loja}.\n\n'
                f'Base: {checklist.inventario.base.nome}\n'
                f'Finalizado por: {usuario.get_username()}'
            ),
            usuario=usuario,
            tipo='OPERACIONAL',
            bases=[checklist.inventario.base],
            empresa=checklist.inventario.base.empresa,
        )

    @staticmethod
    def status_equipamento(equipamento, status_anterior, status_novo, usuario, motivo=''):
        descricao = equipamento.produto.descricao if equipamento.produto else str(equipamento.id)
        regional = equipamento.regional
        mensagem = (
            f'O status do equipamento {descricao} foi alterado.\n\n'
            f'Base: {regional.nome if regional else "-"}\n'
            f'Patrimonio: {equipamento.patrimonio or "N/A"}\n'
            f'Serie: {equipamento.numero_serie or "N/A"}\n'
            f'Status anterior: {status_anterior or "-"}\n'
            f'Novo status: {status_novo}'
        )
        if motivo:
            mensagem = f'{mensagem}\nMotivo: {motivo}'

        return ComunicadoService.criar_acao(
            titulo='Status de equipamento alterado',
            mensagem=mensagem,
            usuario=usuario,
            tipo='MANUTENCAO' if status_novo in ('MANUTENCAO', 'SICK') else 'OPERACIONAL',
            bases=[regional] if regional else None,
            empresa=regional.empresa if regional else None,
        )

    @staticmethod
    def emp_item_reservado(emp, usuario=None):
        usuario = usuario or getattr(emp, 'solicitado_por', None)
        return ComunicadoService.criar_acao(
            titulo='Emprestimo iniciado',
            mensagem=(
                f'{emp.regional_origem.nome} reservou equipamentos para '
                f'{emp.regional_destino.nome}.'
            ),
            tipo='OPERACIONAL',
            usuario=usuario,
            bases=[emp.regional_origem, emp.regional_destino],
            empresa=emp.regional_origem.empresa,
        )

    @staticmethod
    def emp_enviado(emp, usuario=None):
        usuario = usuario or getattr(emp, 'solicitado_por', None)
        return ComunicadoService.criar_acao(
            titulo='Equipamentos enviados',
            mensagem=(
                f'Equipamentos enviados de {emp.regional_origem.nome} '
                f'para {emp.regional_destino.nome}.'
            ),
            tipo='OPERACIONAL',
            usuario=usuario,
            bases=[emp.regional_origem, emp.regional_destino],
            empresa=emp.regional_origem.empresa,
        )

    @staticmethod
    def emp_divergencia(emp, usuario=None):
        usuario = usuario or getattr(emp, 'solicitado_por', None)
        return ComunicadoService.criar_acao(
            titulo='Divergencia no emprestimo',
            mensagem=f'Divergencia detectada no emprestimo {emp.protocolo}.',
            tipo='URGENTE',
            usuario=usuario,
            bases=[emp.regional_origem, emp.regional_destino],
            empresa=emp.regional_origem.empresa,
        )

    @staticmethod
    def emp_recebido(emprestimo, usuario):
        return ComunicadoService.criar_acao(
            titulo='Emprestimo recebido',
            mensagem=(
                f'{emprestimo.regional_destino.nome} confirmou o recebimento '
                f'do emprestimo {emprestimo.protocolo}.'
            ),
            tipo='OPERACIONAL',
            usuario=usuario,
            enviar_para_todos=False,
            bases=[emprestimo.regional_origem, emprestimo.regional_destino],
            empresa=emprestimo.regional_origem.empresa,
        )

    @staticmethod
    def emp_devolucao(emp, usuario=None):
        usuario = usuario or getattr(emp, 'solicitado_por', None)
        return ComunicadoService.criar_acao(
            titulo='Emprestimo finalizado',
            mensagem=(
                f'Devolucao concluida entre {emp.regional_origem.nome} '
                f'e {emp.regional_destino.nome}.'
            ),
            tipo='OPERACIONAL',
            usuario=usuario,
            bases=[emp.regional_origem, emp.regional_destino],
            empresa=emp.regional_origem.empresa,
        )

    @staticmethod
    def emp_devolucao_pendente(emprestimo, usuario):
        return ComunicadoService.criar_acao(
            titulo='Devolucao de emprestimo iniciada',
            mensagem=(
                f'A base "{emprestimo.regional_destino.nome}" registrou a devolucao '
                f'do emprestimo {emprestimo.protocolo}. '
                f'Aguardando confirmacao da base "{emprestimo.regional_origem.nome}".'
            ),
            tipo='OPERACIONAL',
            usuario=usuario,
            enviar_para_todos=False,
            bases=[emprestimo.regional_origem, emprestimo.regional_destino],
            empresa=emprestimo.regional_origem.empresa,
        )
