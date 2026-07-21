from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from estoque.models import Comunicado, Equipamento, Historico, Sick
from estoque.services.comunicado_service import ComunicadoService


class ComunicadoSickService:
    """Cria o comunicado administrativo dentro da transação do fluxo."""

    @staticmethod
    def notificar_admins(*, sick, acao, usuario, etapa_anterior=None, etapa_nova=None, detalhes=None):
        equipamento = sick.equipamento
        destinatarios = ComunicadoService.usuarios_por_bases(
            [equipamento.regional],
            incluir_admins=True,
        )
        nome_usuario = usuario.get_full_name() or usuario.get_username()
        dados = {
            'sick_id': sick.pk,
            'equipamento_id': equipamento.pk,
            'etapa_anterior': etapa_anterior,
            'etapa_nova': etapa_nova,
            'usuario_id': usuario.pk,
            'usuario_nome': nome_usuario,
            'data_acao': timezone.now().isoformat(),
            **(detalhes or {}),
        }
        url = f"{reverse('estoque:sick')}?sick={sick.pk}"
        produto = equipamento.produto
        mensagem = (
            f'Equipamento: {produto.descricao if produto else equipamento.codigo}\n'
            f'Modelo: {produto.modelo if produto else "N/A"}\n'
            f'Série: {equipamento.numero_serie or "N/A"}\n'
            f'Patrimônio: {equipamento.patrimonio or "N/A"}\n'
            f'Empresa: {equipamento.regional.empresa.nome}\n'
            f'Base: {equipamento.regional.nome}\n'
            f'Etapa anterior: {etapa_anterior or "-"}\n'
            f'Nova etapa: {etapa_nova or sick.etapa}\n'
            f'Responsável: {nome_usuario}\n'
            f'Data: {timezone.localtime().strftime("%d/%m/%Y %H:%M")}\n'
        )
        observacao = (detalhes or {}).get('observacao')
        if observacao:
            mensagem += f'Observação: {observacao}\n'
        mensagem += f'Link: {url}'

        comunicado = Comunicado.objects.create(
            titulo=acao,
            mensagem=mensagem,
            tipo='MANUTENCAO',
            criado_por=usuario,
            empresa=equipamento.regional.empresa,
            permitir_limpar=False,
            dados=dados,
            url=url,
        )
        comunicado.usuarios.set(destinatarios)
        return comunicado


class SickService:
    TRANSICOES = {
        'enviar_para_manutencao': (Sick.Etapa.IDENTIFICADO, Sick.Etapa.EM_TRANSITO),
        'confirmar_recebimento': (Sick.Etapa.EM_TRANSITO, Sick.Etapa.RECEBIDO),
        'iniciar_avaliacao': (Sick.Etapa.RECEBIDO, Sick.Etapa.EM_AVALIACAO),
        'iniciar_manutencao': (Sick.Etapa.EM_AVALIACAO, Sick.Etapa.EM_MANUTENCAO),
        'concluir_manutencao': (Sick.Etapa.EM_MANUTENCAO, Sick.Etapa.AGUARDANDO_RETORNO),
        'confirmar_retorno': (Sick.Etapa.AGUARDANDO_RETORNO, Sick.Etapa.FINALIZADO),
    }

    @staticmethod
    def _perfil(usuario):
        perfil = getattr(usuario, 'perfil', None)
        if perfil is None:
            raise PermissionDenied('Usuário sem perfil de acesso.')
        return perfil

    @classmethod
    def _validar_acesso_base(cls, usuario, equipamento):
        perfil = cls._perfil(usuario)
        if perfil.is_admin:
            return perfil
        if not perfil.regionais.filter(pk=equipamento.regional_id).exists():
            raise PermissionDenied('Usuário sem acesso à base do equipamento.')
        if perfil.empresa_id and perfil.empresa_id != equipamento.regional.empresa_id:
            raise PermissionDenied('Equipamento pertence a outra empresa.')
        return perfil

    @classmethod
    def _validar_permissao(cls, usuario, equipamento, *, tipo, permissao=None):
        perfil = cls._perfil(usuario)
        if perfil.is_admin:
            return
        if tipo == 'manutencao':
            if usuario.username == 'rafael.ribeiro':
                return
            if permissao == 'receber_equipamento_manutencao':
                raise PermissionDenied(
                    'Somente Rafael ou um administrador pode confirmar o recebimento.'
                )
            if permissao and usuario.has_perm(f'estoque.{permissao}'):
                return
            raise PermissionDenied('Usuário sem permissão para esta etapa do SICK.')

        perfil = cls._validar_acesso_base(usuario, equipamento)
        if tipo == 'base' and (perfil.is_gestor or perfil.is_operador):
            return
        raise PermissionDenied('Usuário sem permissão para esta etapa do SICK.')

    @classmethod
    def _validar_envio_pela_base(cls, usuario, equipamento):
        perfil = cls._validar_acesso_base(usuario, equipamento)
        if (
            usuario.username == 'rafael.ribeiro' or
            not (perfil.is_gestor or perfil.is_operador)
        ):
            raise PermissionDenied(
                'O envio para manutenção deve ser registrado por um gestor ou usuário da base.'
            )

    @staticmethod
    def _texto_obrigatorio(valor, nome):
        valor = (valor or '').strip()
        if not valor:
            raise ValidationError({nome: 'Este campo é obrigatório.'})
        return valor

    @staticmethod
    def _historico(*, sick, usuario, tipo, etapa_anterior, etapa_nova, detalhes=None):
        equipamento = sick.equipamento
        Historico.objects.create(
            equipamento=equipamento,
            tipo_acao=tipo,
            usuario=usuario,
            detalhes={
                'sick_id': sick.pk,
                'etapa_anterior': etapa_anterior,
                'etapa_nova': etapa_nova,
                'origem': equipamento.regional.nome,
                'data_acao': timezone.now().isoformat(),
                'usuario_id': usuario.pk,
                'usuario_nome': usuario.get_full_name() or usuario.get_username(),
                **(detalhes or {}),
            },
        )

    @staticmethod
    def _carregar_sick(sick_id):
        sick = Sick.objects.select_for_update().get(pk=sick_id)
        sick.equipamento = Equipamento.objects.select_for_update(of=('self',)).select_related(
            'produto', 'regional__empresa'
        ).get(pk=sick.equipamento_id)
        return sick

    @staticmethod
    def _validar_etapa(sick, esperada):
        if sick.etapa != esperada:
            raise ValidationError(
                f'Transição inválida: etapa atual {sick.get_etapa_display()}; '
                f'esperada {Sick.Etapa(esperada).label}.'
            )

    @classmethod
    @transaction.atomic
    def marcar_como_sick(cls, *, equipamento_id, usuario, categoria, motivo, observacao=''):
        equipamento = Equipamento.objects.select_for_update(of=('self',)).select_related(
            'produto', 'regional__empresa'
        ).get(pk=equipamento_id)
        cls._validar_permissao(usuario, equipamento, tipo='base')
        if equipamento.status in {'SICK', 'MANUTENCAO', 'INATIVO', 'BAIXA', 'EM_TRANSITO', 'RESERVADO_TRANSFERENCIA'}:
            raise ValidationError('Equipamento indisponível para abertura de SICK.')
        if Sick.objects.filter(equipamento=equipamento, ativo=True).exists():
            raise ValidationError('Já existe um SICK ativo para este equipamento.')

        motivo = cls._texto_obrigatorio(motivo, 'motivo')
        categoria = cls._texto_obrigatorio(categoria, 'categoria')
        observacao = cls._texto_obrigatorio(observacao, 'observacao')
        sick = Sick.objects.create(
            equipamento=equipamento,
            categoria=categoria,
            motivo=motivo,
            descricao=observacao,
            etapa=Sick.Etapa.IDENTIFICADO,
            ativo=True,
        )
        equipamento.status = 'SICK'
        equipamento.save(update_fields=['status', 'data_atualizacao'])
        detalhes = {'categoria': categoria, 'motivo': motivo, 'observacao': observacao}
        cls._historico(
            sick=sick, usuario=usuario, tipo='SICK', etapa_anterior=None,
            etapa_nova=Sick.Etapa.IDENTIFICADO, detalhes=detalhes,
        )
        ComunicadoSickService.notificar_admins(
            sick=sick, acao='Equipamento marcado como SICK', usuario=usuario,
            etapa_nova=Sick.Etapa.IDENTIFICADO, detalhes=detalhes,
        )
        return sick

    @classmethod
    @transaction.atomic
    def atualizar_informacoes(cls, *, sick_id, usuario, categoria, motivo, observacao=''):
        sick = cls._carregar_sick(sick_id)
        cls._validar_acesso_base(usuario, sick.equipamento)
        if sick.etapa == Sick.Etapa.FINALIZADO:
            raise ValidationError('Um SICK finalizado não pode ser editado sem reabertura.')
        categoria = cls._texto_obrigatorio(categoria, 'categoria')
        motivo = cls._texto_obrigatorio(motivo, 'motivo')
        observacao = cls._texto_obrigatorio(observacao, 'observacao')
        sick.categoria = categoria
        sick.motivo = motivo
        sick.descricao = observacao
        sick.save(update_fields=['categoria', 'motivo', 'descricao'])
        detalhes = {'categoria': categoria, 'motivo': motivo, 'observacao': observacao}
        cls._historico(
            sick=sick, usuario=usuario, tipo='SICK_ATUALIZADO',
            etapa_anterior=sick.etapa, etapa_nova=sick.etapa, detalhes=detalhes,
        )
        ComunicadoSickService.notificar_admins(
            sick=sick, acao='Informações do SICK atualizadas', usuario=usuario,
            etapa_anterior=sick.etapa, etapa_nova=sick.etapa, detalhes=detalhes,
        )
        return sick

    @classmethod
    @transaction.atomic
    def enviar_para_manutencao(cls, *, sick_id, usuario, destino, transportadora='', protocolo='', observacao=''):
        sick = cls._carregar_sick(sick_id)
        cls._validar_envio_pela_base(usuario, sick.equipamento)
        cls._validar_etapa(sick, Sick.Etapa.IDENTIFICADO)
        destino = cls._texto_obrigatorio(destino, 'destino_manutencao')
        anterior = sick.etapa
        sick.etapa = Sick.Etapa.EM_TRANSITO
        sick.enviado_manutencao_em = timezone.now()
        sick.enviado_manutencao_por = usuario
        sick.destino_manutencao = destino
        sick.transportadora_ou_portador = (transportadora or '').strip()
        sick.protocolo_envio = (protocolo or '').strip()
        if observacao:
            sick.observacao_tecnica = observacao.strip()
        sick.save()
        detalhes = {'destino': destino, 'protocolo': protocolo, 'transportadora': transportadora, 'observacao': observacao}
        cls._registrar_transicao(sick, usuario, anterior, 'SICK_ENVIO_MANUTENCAO', 'Equipamento enviado para manutenção', detalhes)
        return sick

    @classmethod
    @transaction.atomic
    def confirmar_recebimento(cls, *, sick_id, usuario, observacao=''):
        sick = cls._carregar_sick(sick_id)
        cls._validar_permissao(usuario, sick.equipamento, tipo='manutencao', permissao='receber_equipamento_manutencao')
        cls._validar_etapa(sick, Sick.Etapa.EM_TRANSITO)
        anterior = sick.etapa
        sick.etapa = Sick.Etapa.RECEBIDO
        sick.recebido_manutencao_em = timezone.now()
        sick.recebido_manutencao_por = usuario
        sick.save()
        cls._registrar_transicao(sick, usuario, anterior, 'SICK_RECEBIMENTO_MANUTENCAO', 'Equipamento recebido pela manutenção', {'observacao': observacao})
        return sick

    @classmethod
    @transaction.atomic
    def iniciar_avaliacao(cls, *, sick_id, usuario, observacao=''):
        sick = cls._carregar_sick(sick_id)
        cls._validar_permissao(usuario, sick.equipamento, tipo='manutencao', permissao='avaliar_equipamento_sick')
        cls._validar_etapa(sick, Sick.Etapa.RECEBIDO)
        anterior = sick.etapa
        sick.etapa = Sick.Etapa.EM_AVALIACAO
        sick.avaliacao_iniciada_em = timezone.now()
        sick.avaliacao_iniciada_por = usuario
        sick.save()
        cls._registrar_transicao(sick, usuario, anterior, 'SICK_AVALIACAO', 'Avaliação técnica iniciada', {'observacao': observacao})
        return sick

    @classmethod
    @transaction.atomic
    def iniciar_manutencao(
        cls, *, sick_id, usuario, causa, diagnostico, observacao,
        previsao_retorno=None,
    ):
        sick = cls._carregar_sick(sick_id)
        cls._validar_permissao(usuario, sick.equipamento, tipo='manutencao', permissao='iniciar_manutencao_equipamento')
        cls._validar_etapa(sick, Sick.Etapa.EM_AVALIACAO)
        causa = cls._texto_obrigatorio(causa, 'causa_identificada')
        diagnostico = cls._texto_obrigatorio(diagnostico, 'diagnostico')
        observacao = cls._texto_obrigatorio(observacao, 'observacao_tecnica')
        previsao = None
        if previsao_retorno:
            previsao = parse_date(str(previsao_retorno))
            if previsao is None:
                raise ValidationError({'previsao_retorno': 'Informe uma data válida.'})
        anterior = sick.etapa
        sick.etapa = Sick.Etapa.EM_MANUTENCAO
        sick.status_final = 'MANUTENCAO'
        sick.causa_identificada = causa
        sick.diagnostico = diagnostico
        sick.observacao_tecnica = observacao
        sick.previsao_retorno = previsao
        sick.manutencao_iniciada_em = timezone.now()
        sick.manutencao_iniciada_por = usuario
        sick.equipamento.status = 'MANUTENCAO'
        sick.equipamento.save(update_fields=['status', 'data_atualizacao'])
        sick.save()
        cls._registrar_transicao(
            sick, usuario, anterior, 'MANUTENCAO_INICIADA', 'Manutenção iniciada',
            {
                'causa': causa,
                'diagnostico': diagnostico,
                'observacao': observacao,
                'previsao_retorno': previsao.isoformat() if previsao else None,
            },
        )
        return sick

    @classmethod
    @transaction.atomic
    def concluir_manutencao(cls, *, sick_id, usuario, solucao, resultado, apto_retorno, observacao=''):
        sick = cls._carregar_sick(sick_id)
        cls._validar_permissao(usuario, sick.equipamento, tipo='manutencao', permissao='concluir_manutencao_equipamento')
        cls._validar_etapa(sick, Sick.Etapa.EM_MANUTENCAO)
        solucao = cls._texto_obrigatorio(solucao, 'solucao_aplicada')
        resultado = cls._texto_obrigatorio(resultado, 'resultado_manutencao')
        apto = str(apto_retorno).lower() in {'1', 'true', 'sim', 'yes'}
        sick.solucao_aplicada = solucao
        sick.resultado_manutencao = resultado
        sick.apto_retorno = apto
        sick.manutencao_concluida_em = timezone.now()
        sick.manutencao_concluida_por = usuario
        if observacao:
            sick.observacao_resolucao = observacao.strip()
        anterior = sick.etapa
        detalhes = {'solucao': solucao, 'resultado': resultado, 'apto_retorno': apto, 'observacao': observacao}
        if not apto:
            sick.save()
            cls._historico(sick=sick, usuario=usuario, tipo='MANUTENCAO_ATUALIZADA', etapa_anterior=anterior, etapa_nova=anterior, detalhes=detalhes)
            ComunicadoSickService.notificar_admins(sick=sick, acao='Equipamento definido como sem reparo', usuario=usuario, etapa_anterior=anterior, etapa_nova=anterior, detalhes=detalhes)
            return sick
        sick.etapa = Sick.Etapa.AGUARDANDO_RETORNO
        sick.status_final = 'SICK'
        sick.equipamento.status = 'SICK'
        sick.equipamento.save(update_fields=['status', 'data_atualizacao'])
        sick.save()
        cls._registrar_transicao(sick, usuario, anterior, 'MANUTENCAO_CONCLUIDA', 'Manutenção concluída; aguardando retorno', detalhes)
        return sick

    @classmethod
    @transaction.atomic
    def inativar_sem_reparo(cls, *, sick_id, usuario, motivo):
        sick = cls._carregar_sick(sick_id)
        cls._validar_permissao(
            usuario, sick.equipamento, tipo='manutencao',
            permissao='concluir_manutencao_equipamento',
        )
        cls._validar_etapa(sick, Sick.Etapa.EM_MANUTENCAO)
        if sick.apto_retorno is not False:
            raise ValidationError(
                'Registre primeiro a conclusão da manutenção como sem condição de retorno.'
            )
        motivo = cls._texto_obrigatorio(motivo, 'motivo_inativacao')
        anterior = sick.etapa
        agora = timezone.now()
        sick.etapa = Sick.Etapa.FINALIZADO
        sick.ativo = False
        sick.status_final = 'INATIVO'
        sick.data_resolucao = agora
        sick.resolvido_por = usuario
        sick.observacao_resolucao = motivo
        sick.manutencao_concluida_em = sick.manutencao_concluida_em or agora
        sick.manutencao_concluida_por = sick.manutencao_concluida_por or usuario
        sick.equipamento.status = 'INATIVO'
        sick.equipamento.save(update_fields=['status', 'data_atualizacao'])
        sick.save()
        cls._registrar_transicao(
            sick, usuario, anterior, 'SICK_INATIVADO',
            'Equipamento inativado pela manutenção por ausência de reparo',
            {'motivo': motivo, 'observacao': motivo},
        )
        return sick

    @classmethod
    @transaction.atomic
    def confirmar_retorno(cls, *, sick_id, usuario, observacao=''):
        sick = cls._carregar_sick(sick_id)
        cls._validar_permissao(usuario, sick.equipamento, tipo='base', permissao='confirmar_retorno_equipamento')
        cls._validar_etapa(sick, Sick.Etapa.AGUARDANDO_RETORNO)
        anterior = sick.etapa
        sick.etapa = Sick.Etapa.FINALIZADO
        sick.ativo = False
        sick.data_resolucao = timezone.now()
        sick.resolvido_por = usuario
        sick.retorno_confirmado_em = timezone.now()
        sick.retorno_confirmado_por = usuario
        sick.status_final = 'ATIVO'
        sick.equipamento.status = 'ATIVO'
        sick.equipamento.save(update_fields=['status', 'data_atualizacao'])
        sick.save()
        cls._registrar_transicao(sick, usuario, anterior, 'SICK_RETORNO_CONFIRMADO', 'Retorno do equipamento confirmado pela base', {'observacao': observacao})
        return sick

    @classmethod
    def _registrar_transicao(cls, sick, usuario, anterior, tipo_historico, titulo, detalhes):
        cls._historico(
            sick=sick, usuario=usuario, tipo=tipo_historico,
            etapa_anterior=anterior, etapa_nova=sick.etapa, detalhes=detalhes,
        )
        ComunicadoSickService.notificar_admins(
            sick=sick, acao=titulo, usuario=usuario,
            etapa_anterior=anterior, etapa_nova=sick.etapa, detalhes=detalhes,
        )
