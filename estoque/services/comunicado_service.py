from datetime import timedelta

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from estoque.models import Base, Comunicado, Sick
from estoque.policies.compras import GruposCorporativos


class ComunicadoService:
    DIAS_EXPIRACAO_PADRAO = 30

    @staticmethod
    def expira_em_padrao():
        return timezone.now() + timedelta(days=ComunicadoService.DIAS_EXPIRACAO_PADRAO)

    @staticmethod
    def admins_para_empresas(empresas):
        """Administradores explicitamente vinculados às empresas informadas.

        Superusers continuam recebendo alertas de plataforma, mas um Admin de
        tenant nunca é incluído apenas por possuir o papel ``admin``.
        """
        if empresas is None:
            empresas_ids = set()
        elif hasattr(empresas, 'values_list'):
            empresas_ids = set(empresas.values_list('pk', flat=True))
        else:
            empresas_ids = {
                getattr(empresa, 'pk', empresa)
                for empresa in empresas
                if empresa is not None
            }

        filtro = Q(is_superuser=True)
        if empresas_ids:
            filtro |= Q(
                perfil__role='admin',
                perfil__empresa_id__in=empresas_ids,
            )
            filtro |= Q(
                perfil__role='admin',
                perfil__empresas_acesso_adicional__id__in=empresas_ids,
            )
        return User.objects.filter(is_active=True).filter(filtro).distinct()

    @staticmethod
    def admins_para_empresa(empresa):
        return ComunicadoService.admins_para_empresas([empresa])

    @staticmethod
    def usuarios_por_bases(bases, incluir_admins=True, excluir_usuario=None):
        bases_ids = []
        empresas_ids = set()

        if bases is None:
            bases_ids = []
        elif hasattr(bases, 'values_list'):
            bases_ids = list(bases.values_list('id', flat=True))
            empresas_ids.update(bases.values_list('empresa_id', flat=True))
        else:
            for base in bases:
                if isinstance(base, Base):
                    bases_ids.append(base.id)
                    empresas_ids.add(base.empresa_id)
                elif base:
                    bases_ids.append(base)

        if bases_ids and not empresas_ids:
            empresas_ids.update(
                Base.objects.filter(pk__in=bases_ids).values_list(
                    'empresa_id', flat=True,
                )
            )

        filtros = Q()
        if bases_ids:
            filtros |= Q(perfil__regionais__id__in=bases_ids)

        if incluir_admins:
            filtros |= Q(
                pk__in=ComunicadoService.admins_para_empresas(
                    empresas_ids
                ).values('pk')
            )

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
        incluir_autor=True,
        dados=None,
        url='',
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
            dados=dados,
            url=url,
        )

        if enviar_para_todos:
            destinatarios = User.objects.filter(is_active=True)
            if empresa:
                destinatarios = destinatarios.filter(
                    Q(perfil__empresa=empresa)
                    | Q(perfil__empresas_acesso_adicional=empresa)
                    | Q(is_superuser=True)
                )
            else:
                # Broadcast realmente global é reservado ao Superuser.
                if not usuario.is_superuser:
                    destinatarios = destinatarios.none()
            comunicado.usuarios.set(destinatarios.distinct())
        else:
            # Toda acao notifica autor, envolvidos e administradores. Essa
            # relacao alimenta o badge de comunicados nao lidos do menu.
            destinatarios_ids = {usuario.pk} if incluir_autor else set()
            if incluir_admins:
                destinatarios_ids.update(
                    ComunicadoService.admins_para_empresas(
                        [empresa] if empresa is not None else []
                    ).values_list('pk', flat=True)
                )
            if usuarios is not None:
                if hasattr(usuarios, 'values_list'):
                    destinatarios_ids.update(usuarios.values_list('pk', flat=True))
                else:
                    destinatarios_ids.update(
                        item.pk for item in usuarios if item is not None
                    )
            if bases is not None:
                destinatarios_ids.update(
                    ComunicadoService.usuarios_por_bases(
                        bases,
                        incluir_admins=incluir_admins,
                    ).values_list('pk', flat=True)
                )
            comunicado.usuarios.set(
                User.objects.filter(is_active=True, pk__in=destinatarios_ids)
            )

        transaction.on_commit(
            lambda comunicado_id=comunicado.id: __import__(
                'estoque.services.comunicacoes.dispatcher',
                fromlist=['ComunicacaoDispatcher'],
            ).ComunicacaoDispatcher.criar_entregas(comunicado_id)
        )

        return comunicado

    @staticmethod
    def auditoria_aberta(auditoria_base, usuario):
        return ComunicadoService.criar_acao(
            titulo=f'Auditoria aberta — {auditoria_base.base.nome}',
            mensagem=(
                f'A coleta da campanha {auditoria_base.campanha.nome} foi iniciada '
                f'na base {auditoria_base.base.nome}.'
            ),
            usuario=usuario,
            bases=[auditoria_base.base],
            empresa=auditoria_base.campanha.empresa,
            dados={'template_codigo': 'auditoria_aberta', 'auditoria_base_id': auditoria_base.pk},
            url=f'/auditorias/bases/{auditoria_base.pk}/coleta/',
        )

    @staticmethod
    def auditoria_enviada(auditoria_base, usuario):
        administradores = ComunicadoService.admins_para_empresa(
            auditoria_base.campanha.empresa
        )
        return ComunicadoService.criar_acao(
            titulo=f'Auditoria enviada — {auditoria_base.base.nome}',
            mensagem=(
                f'A auditoria da base {auditoria_base.base.nome} foi enviada para análise. '
                f'Status: {auditoria_base.get_status_display()}.'
            ),
            usuario=usuario,
            tipo='OPERACIONAL',
            usuarios=administradores,
            empresa=auditoria_base.campanha.empresa,
            dados={
                'template_codigo': 'auditoria_enviada',
                'auditoria_base_id': auditoria_base.pk,
            },
            url=f'/auditorias/bases/{auditoria_base.pk}/divergencias/',
        )

    @staticmethod
    def auditoria_finalizada(auditoria_base, usuario):
        tem_divergencias = auditoria_base.divergencias.exclude(
            status__in=['RESOLVIDA', 'CANCELADA']
        ).exists()
        return ComunicadoService.criar_acao(
            titulo=f'Resultado da auditoria — {auditoria_base.base.nome}',
            mensagem=(
                f'O resultado final da auditoria da base {auditoria_base.base.nome} foi liberado. '
                f'Status: {auditoria_base.get_status_display()}.'
            ),
            usuario=usuario,
            tipo='URGENTE' if tem_divergencias else 'OPERACIONAL',
            bases=[auditoria_base.base],
            empresa=auditoria_base.campanha.empresa,
            dados={
                'template_codigo': 'auditoria_resultado_final',
                'auditoria_base_id': auditoria_base.pk,
            },
            url=f'/auditorias/bases/{auditoria_base.pk}/divergencias/',
        )

    @staticmethod
    def auditoria_correcao_solicitada(auditoria_base, usuario):
        prazo = timezone.localtime(auditoria_base.prazo_correcao_em).strftime('%d/%m/%Y às %H:%M')
        return ComunicadoService.criar_acao(
            titulo=f'Correções solicitadas — {auditoria_base.base.nome}',
            mensagem=(
                f'O administrador solicitou correções na auditoria da base '
                f'{auditoria_base.base.nome}. Prazo: {prazo}. '
                f'Orientações: {auditoria_base.orientacoes_correcao}'
            ),
            usuario=usuario,
            tipo='URGENTE',
            bases=[auditoria_base.base],
            empresa=auditoria_base.campanha.empresa,
            dados={
                'template_codigo': 'auditoria_correcao_solicitada',
                'auditoria_base_id': auditoria_base.pk,
            },
            url=f'/auditorias/bases/{auditoria_base.pk}/divergencias/',
        )

    @staticmethod
    def auditoria_equipamento_mantido(divergencia, resolucao, usuario):
        return ComunicadoService.criar_acao(
            titulo='Equipamento regularizado por auditoria',
            mensagem=(
                f'O equipamento {divergencia.equipamento.codigo} foi mantido na base '
                f'{divergencia.base_encontrada.nome}. Justificativa: {resolucao.justificativa}'
            ),
            usuario=usuario,
            bases=[resolucao.base_anterior, resolucao.nova_base],
            empresa=divergencia.auditoria_base.campanha.empresa,
            dados={'template_codigo': 'auditoria_equipamento_mantido', 'divergencia_id': divergencia.pk},
            url=f'/auditorias/divergencias/{divergencia.pk}/',
        )

    @staticmethod
    def auditoria_transferencia_criada(divergencia, transferencia, usuario):
        return ComunicadoService.criar_acao(
            titulo=f'Transferência de auditoria {transferencia.protocolo}',
            mensagem=(
                f'A transferência do equipamento {divergencia.equipamento.codigo} foi criada de '
                f'{transferencia.regional_origem.nome} para {transferencia.regional_destino.nome}.'
            ),
            usuario=usuario,
            bases=[transferencia.regional_origem, transferencia.regional_destino],
            empresa=transferencia.regional_destino.empresa,
            dados={'template_codigo': 'auditoria_transferencia_criada', 'divergencia_id': divergencia.pk},
            url=f'/transferencias/{transferencia.pk}/',
        )

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
            from estoque.policies.tenant_operations import TenantOperationPolicy

            empresa = sick.equipamento.regional.empresa
            candidatos_manutencao = User.objects.filter(
                is_active=True,
                groups__name=GruposCorporativos.SICK_MANUTENCAO,
            ).distinct()
            manutencao_ids = [
                candidato.pk
                for candidato in candidatos_manutencao
                if TenantOperationPolicy.sick(
                    candidato,
                    Sick.objects.filter(pk=sick.pk),
                ).exists()
            ]
            destinatarios_ids = set(manutencao_ids)
            destinatarios_ids.update(
                ComunicadoService.admins_para_empresa(empresa).values_list(
                    'pk', flat=True,
                )
            )
            destinatarios = User.objects.filter(
                pk__in=destinatarios_ids,
                is_active=True,
            )
            if not destinatarios.exists():
                continue
            criador = (
                destinatarios.filter(
                    groups__name=GruposCorporativos.SICK_MANUTENCAO,
                ).first()
                or destinatarios.filter(is_superuser=True).first()
                or destinatarios.first()
            )
            titulo = (
                f'Manutenção prevista para amanhã — SICK #{sick.id}'
            )
            if Comunicado.objects.filter(titulo__iexact=titulo).exists():
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
                empresa=empresa,
                incluir_admins=False,
                permitir_limpar=False,
                expira_em=timezone.now() + timedelta(days=3),
            )
            comunicados.append(comunicado)
        return comunicados

    @staticmethod
    def usuarios_ciclo_compras(empresa, solicitante=None):
        from insumos.constants import GruposInsumos

        filtros = (
            Q(groups__name=GruposInsumos.COMPRAS) |
            Q(groups__name=GruposInsumos.FINANCEIRO)
        )
        if solicitante:
            filtros |= Q(pk=solicitante.pk)
        usuarios_funcionais = User.objects.filter(
            is_active=True,
        ).filter(filtros).filter(
            Q(perfil__empresa=empresa)
            | Q(perfil__empresas_acesso_adicional=empresa)
        )
        usuarios_ids = set(
            usuarios_funcionais.values_list('pk', flat=True)
        )
        usuarios_ids.update(
            ComunicadoService.admins_para_empresa(empresa).values_list(
                'pk', flat=True,
            )
        )
        return User.objects.filter(pk__in=usuarios_ids, is_active=True)

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
            usuarios=ComunicadoService.usuarios_ciclo_compras(
                solicitacao.base.empresa,
                solicitacao.solicitante,
            ),
            empresa=solicitacao.base.empresa,
            incluir_admins=False,
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
            usuarios=ComunicadoService.usuarios_ciclo_compras(
                solicitacao.base.empresa,
                solicitacao.solicitante,
            ),
            empresa=solicitacao.base.empresa,
            incluir_admins=False,
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
