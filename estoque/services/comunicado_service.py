from datetime import timedelta

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from estoque.models import Base, Comunicado, Sick


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
    @transaction.atomic
    def notificar_manutencoes_previstas(data_referencia=None):
        data_referencia = data_referencia or timezone.localdate()
        data_previsao = data_referencia + timedelta(days=1)
        destinatarios = User.objects.filter(is_active=True).filter(
            Q(perfil__role='admin') |
            Q(username='rafael.ribeiro')
        ).distinct()
        if not destinatarios.exists():
            return []

        criador = destinatarios.filter(username='rafael.ribeiro').first()
        if criador is None:
            criador = destinatarios.filter(perfil__role='admin').first()

        comunicados = []
        manutencoes = (
            Sick.objects
            .select_for_update(of=('self',))
            .filter(
                ativo=True,
                status_final='MANUTENCAO',
                previsao_retorno=data_previsao,
            )
            .select_related('equipamento__produto', 'equipamento__regional__empresa')
        )
        for sick in manutencoes:
            titulo = (
                f'Manutenção prevista para amanhã — SICK #{sick.id}'
            )
            if Comunicado.objects.filter(titulo=titulo).exists():
                continue

            equipamento = sick.equipamento
            comunicado = ComunicadoService.criar_acao(
                titulo=titulo,
                mensagem=(
                    'A previsão de retorno deste equipamento é amanhã.\n\n'
                    f'Equipamento: {equipamento.produto.descricao if equipamento.produto else equipamento.codigo}\n'
                    f'Código: {equipamento.codigo}\n'
                    f'Patrimônio: {equipamento.patrimonio or "N/A"}\n'
                    f'Série: {equipamento.numero_serie or "N/A"}\n'
                    f'Base: {equipamento.regional.nome}\n'
                    f'Previsão: {data_previsao.strftime("%d/%m/%Y")}\n'
                    f'Motivo: {sick.motivo or "Não informado"}'
                ),
                usuario=criador,
                tipo='MANUTENCAO',
                usuarios=destinatarios,
                empresa=equipamento.regional.empresa,
                permitir_limpar=False,
                expira_em=timezone.now() + timedelta(days=3),
            )
            comunicados.append(comunicado)
        return comunicados

    @staticmethod
    def usuarios_ciclo_compras(solicitante=None):
        from insumos.constants import GruposInsumos

        filtros = (
            Q(perfil__role='admin') |
            Q(groups__name=GruposInsumos.COMPRAS) |
            Q(groups__name=GruposInsumos.FINANCEIRO)
        )
        if solicitante:
            filtros |= Q(pk=solicitante.pk)
        return User.objects.filter(is_active=True).filter(filtros).distinct()

    @staticmethod
    def solicitacao_insumo_criada(solicitacao, usuario):
        itens = list(solicitacao.itens.select_related('insumo').all())
        linhas = '\n'.join(
            f'- {item.insumo.descricao}: {item.quantidade:g} {item.insumo.unidade_medida}'
            for item in itens
        )
        return ComunicadoService.criar_acao(
            titulo=f'Nova solicitação de insumos {solicitacao.protocolo}',
            mensagem=(
                f'{usuario.get_full_name() or usuario.get_username()} criou uma solicitação de insumos.\n\n'
                f'Base: {solicitacao.base.nome}\n'
                f'Prioridade: {solicitacao.get_prioridade_display()}\n'
                f'Justificativa: {solicitacao.justificativa or "-"}\n\n'
                f'Itens:\n{linhas}'
            ),
            usuario=usuario,
            tipo='URGENTE' if solicitacao.prioridade == 'URGENTE' else 'OPERACIONAL',
            usuarios=ComunicadoService.usuarios_ciclo_compras(solicitacao.solicitante),
            empresa=solicitacao.base.empresa,
        )

    @staticmethod
    def solicitacao_insumo_decidida(solicitacao, usuario):
        return ComunicadoService.criar_acao(
            titulo=f'Solicitação {solicitacao.protocolo}: {solicitacao.get_status_display()}',
            mensagem=(
                f'A solicitação de insumos foi atualizada.\n\n'
                f'Base: {solicitacao.base.nome}\n'
                f'Solicitante: {solicitacao.solicitante.get_full_name() or solicitacao.solicitante.get_username()}\n'
                f'Status: {solicitacao.get_status_display()}\n'
                f'Responsável: {usuario.get_full_name() or usuario.get_username()}\n'
                f'Observação: {solicitacao.observacao_aprovacao or "-"}'
            ),
            usuario=usuario,
            tipo='URGENTE' if solicitacao.status == 'REPROVADA' else 'OPERACIONAL',
            usuarios=ComunicadoService.usuarios_ciclo_compras(solicitacao.solicitante),
            empresa=solicitacao.base.empresa,
        )

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
