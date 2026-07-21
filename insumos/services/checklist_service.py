from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from insumos.models import (
    ChecklistDiario,
    ChecklistEquipamento,
    ChecklistLoteTag,
    HistoricoInsumo,
    ItemChecklist,
    MovimentacaoTag,
    LoteTag,
    Insumo,
)
from insumos.services.consumo_service import ConsumoService
from insumos.services.movimentacao_service import MovimentacaoService
from estoque.models import Comunicado, Equipamento, Historico, Sick
from estoque.services.comunicado_service import ComunicadoService
from estoque.services.sick_service import SickService
from django.contrib.auth.models import User


class ChecklistService:

    @staticmethod
    @transaction.atomic
    def criar(
        *,
        inventario,
        usuario,
        responsavel=None,
        observacao='',
        quantidade_volumes=0,
        transporte='',
    ):
        return ChecklistDiario.objects.create(
            inventario=inventario,
            data_inicio=timezone.now(),
            criado_por=usuario,
            responsavel=responsavel or usuario,
            observacao=observacao,
            quantidade_volumes=quantidade_volumes,
            transporte=(transporte or '').strip(),
            status='EM_EXECUCAO',
        )


    # INSUMOS
    @staticmethod
    @transaction.atomic
    def adicionar_item(*, checklist, insumo, quantidade_enviada):
        quantidade_enviada = Decimal(str(quantidade_enviada or '0'))
        if quantidade_enviada <= 0:
            return None

        item, criado = ItemChecklist.objects.get_or_create(
            checklist=checklist,
            insumo=insumo,
            defaults={'quantidade_enviada': quantidade_enviada},
        )
        if not criado:
            raise ValueError('Este insumo já foi adicionado ao checklist.')
        return item

    @staticmethod
    @transaction.atomic
    def registrar_envio_item(*, checklist, insumo, quantidade_enviada, usuario):
        quantidade_enviada = Decimal(str(quantidade_enviada or '0'))
        if quantidade_enviada <= 0:
            return None

        saldo = MovimentacaoService.saldo(checklist.inventario.base, insumo)
        if saldo < quantidade_enviada:
            raise ValueError(
                f'Saldo insuficiente para o insumo "{insumo.descricao}". '
                f'Disponível: {saldo}. Solicitado: {quantidade_enviada}.'
            )

        item = ChecklistService.adicionar_item(
            checklist=checklist,
            insumo=insumo,
            quantidade_enviada=quantidade_enviada,
        )
        if item is None:
            return None

        MovimentacaoService.saida(
            base=checklist.inventario.base,
            insumo=insumo,
            quantidade=item.quantidade_enviada,
            usuario=usuario,
            observacao=f'Envio para checklist {checklist.id}',
        )
        return item

    @staticmethod
    def insumos_disponiveis_para_checklist(base):
        insumos = []
        queryset = (
            Insumo.objects
            .filter(ativo=True)
            .select_related('categoria')
            .order_by('descricao')
        )

        for insumo in queryset:
            saldo = MovimentacaoService.saldo(base, insumo)
            if saldo > 0:
                insumos.append({
                    'id': insumo.id,
                    'descricao': insumo.descricao,
                    'categoria': insumo.categoria.nome if insumo.categoria_id else '',
                    'saldo': saldo,
                    'insumo': insumo,
                })

        return insumos

    @staticmethod
    @transaction.atomic
    def atualizar_item(*, item, utilizada, retornada, perdida):
        utilizada = Decimal(str(utilizada or '0'))
        retornada = Decimal(str(retornada or '0'))
        perdida = Decimal(str(perdida or '0'))
        total = utilizada + retornada + perdida

        if total > item.quantidade_enviada:
            raise ValueError('A soma não pode exceder a quantidade enviada.')

        item.quantidade_utilizada = utilizada
        item.quantidade_retornada = retornada
        item.quantidade_perdida = perdida
        item.save(update_fields=[
            'quantidade_utilizada', 'quantidade_retornada', 'quantidade_perdida'
        ])
        return item

    @staticmethod
    @transaction.atomic
    def atualizar_retorno_item(*, item, retornada):
        retornada = Decimal(str(retornada or '0'))

        if retornada < 0:
            raise ValueError('A quantidade retornada não pode ser negativa.')

        if retornada > item.quantidade_enviada:
            raise ValueError('A quantidade retornada não pode exceder a quantidade enviada.')

        item.quantidade_retornada = retornada
        item.quantidade_perdida = Decimal('0')
        item.quantidade_utilizada = item.quantidade_enviada - retornada
        item.status_retorno = 'CONFERIDO'
        item.save(update_fields=[
            'quantidade_utilizada', 'quantidade_retornada',
            'quantidade_perdida', 'status_retorno'
        ])
        return item


    # EQUIPAMENTOS
    @staticmethod
    @transaction.atomic
    def adicionar_equipamento(*, checklist, equipamento, usuario):
        if equipamento.regional_id != checklist.inventario.base_id:
            raise ValueError(
                f'O equipamento {equipamento} não pertence à base do inventário.'
            )
        if equipamento.status != 'ATIVO':
            raise ValueError(
                f'O equipamento {equipamento} não está ativo para envio.'
            )

        item = ChecklistEquipamento.objects.create(
            checklist=checklist,
            equipamento=equipamento,
            tag_saida='',
            tag_volta='',
        )

        equipamento.status = 'EM_USO'
        equipamento.save(update_fields=['status', 'data_atualizacao'])

        HistoricoInsumo.objects.create(
            tipo='CHECKLIST',
            usuario=usuario,
            descricao=f'Equipamento enviado no checklist {checklist.id}.',
            dados={
                'checklist': checklist.id,
                'inventario': str(checklist.inventario),
                'base': checklist.inventario.base.nome,
                'equipamento': equipamento.id,
                'patrimonio': equipamento.patrimonio,
            },
        )
        return item

    @staticmethod
    def _comunicar_admins_equipamento(item_equip, usuario):
        admins = User.objects.filter(perfil__role='admin', is_active=True).distinct()
        if not admins.exists():
            return None

        equipamento = item_equip.equipamento
        descricao = equipamento.produto.descricao if equipamento.produto else str(equipamento.id)
        comunicado = Comunicado.objects.create(
            titulo=f'Ocorrência no checklist #{item_equip.checklist_id}',
            mensagem=(
                f'O equipamento {descricao} '
                f'(Patrimônio: {equipamento.patrimonio}, Série: {equipamento.numero_serie}) '
                f'foi resolvido como {item_equip.get_status_retorno_display()} no retorno do checklist '
                f'#{item_equip.checklist_id}.\n\n'
                f'Observação: {item_equip.motivo_observacao or "-"}'
            ),
            tipo='URGENTE',
            criado_por=usuario,
            enviar_para_todos=False,
            permitir_limpar=False,
            expira_em=ComunicadoService.expira_em_padrao(),
        )
        comunicado.usuarios.set(admins)
        return comunicado

    @staticmethod
    @transaction.atomic
    def resolver_retorno_equipamento(*, item_equip, status_retorno, observacao, usuario):
        status_retorno = (status_retorno or 'PENDENTE').upper()
        observacao = (observacao or '').strip()
        status_validos = {codigo for codigo, _ in ChecklistEquipamento.STATUS_RETORNO}

        if status_retorno not in status_validos:
            raise ValueError('Status de retorno do equipamento inválido.')

        equipamento = item_equip.equipamento
        identificacao = f'{equipamento.patrimonio} ({equipamento.numero_serie})'
        status_anterior = item_equip.status_retorno
        gerar_ocorrencia = status_retorno != status_anterior or not item_equip.resolvido_em

        if status_retorno not in ('RETORNADO', 'PENDENTE') and not observacao:
            raise ValueError(f'Informe a observação para o equipamento {identificacao}.')

        agora = timezone.now()
        item_equip.status_retorno = status_retorno
        item_equip.motivo_observacao = observacao
        item_equip.resolvido_por = usuario if status_retorno != 'PENDENTE' else None
        item_equip.resolvido_em = agora if status_retorno != 'PENDENTE' else None

        if status_retorno == 'RETORNADO':
            if Sick.objects.filter(equipamento=equipamento, ativo=True).exclude(
                etapa=Sick.Etapa.FINALIZADO
            ).exists():
                raise ValueError(
                    'O equipamento possui SICK ativo; confirme o retorno pelo fluxo de manutenção.'
                )
            item_equip.data_retorno = item_equip.data_retorno or agora
            equipamento.status = 'ATIVO'
            equipamento.save(update_fields=['status', 'data_atualizacao'])
        elif status_retorno in ('SICK', 'DANO'):
            item_equip.data_retorno = None
            if gerar_ocorrencia:
                SickService.marcar_como_sick(
                    equipamento_id=equipamento.pk,
                    usuario=usuario,
                    categoria=status_retorno,
                    motivo=observacao,
                    observacao=f'Ocorrência registrada no retorno do checklist #{item_equip.checklist_id}.',
                )
        elif status_retorno in ('PERDA', 'ROUBO'):
            item_equip.data_retorno = None
            equipamento.status = 'INATIVO'
            equipamento.save(update_fields=['status', 'data_atualizacao'])
            if gerar_ocorrencia:
                Sick.objects.create(
                    equipamento=equipamento,
                    categoria=status_retorno,
                    motivo=observacao,
                    descricao=f'Ocorrencia registrada no retorno do checklist #{item_equip.checklist_id}.',
                    ativo=False,
                    status_final='INATIVO',
                    data_resolucao=agora,
                    resolvido_por=usuario,
                )
                ChecklistService._comunicar_admins_equipamento(item_equip, usuario)
        else:
            item_equip.data_retorno = None

        item_equip.save(update_fields=[
            'status_retorno', 'motivo_observacao', 'resolvido_por',
            'resolvido_em', 'data_retorno'
        ])

        if status_retorno != 'PENDENTE' and gerar_ocorrencia:
            Historico.objects.create(
                equipamento=equipamento,
                usuario=usuario,
                tipo_acao='STATUS',
                detalhes={
                    'origem': 'checklist',
                    'checklist': item_equip.checklist_id,
                    'status_retorno': status_retorno,
                    'observacao': observacao,
                    'status_equipamento': equipamento.status,
                },
            )

        return item_equip


    # TAGS
    @staticmethod
    def _validar_numero_dentro_do_lote(lote, numero, campo='Número'):
        if numero is None:
            raise ValueError(f'{campo} não informado.')

        if numero < lote.numero_inicial or numero > lote.numero_final:
            raise ValueError(
                f'{campo} {numero} fora da faixa do lote '
                f'({lote.numero_inicial} até {lote.numero_final}).'
            )

    @staticmethod
    def _quantidade_tags_utilizadas(numero_inicial, numero_final):
        return numero_final - numero_inicial + 1

    @staticmethod
    @transaction.atomic
    def adicionar_lote_tag(*, checklist, lote, numero_inicial_utilizado, usuario, rolo=None, modo_rolo=None):
        """
        Na criação/execução do checklist, a TAG registra apenas o início do intervalo consumido.
        O número final será informado na finalização.
        """
        if lote.base_id != checklist.inventario.base_id:
            raise ValueError('O lote de tags não pertence à base do inventário.')

        if rolo:
            if rolo.lote_id != lote.id:
                raise ValueError('O rolo informado não pertence ao lote selecionado.')
            if rolo.status not in ('DISPONIVEL', 'EM_USO'):
                raise ValueError(
                    f'O rolo {rolo.codigo} do lote {lote.numero_inicial}-{lote.numero_final} não está disponível.'
                )

            if not modo_rolo:
                modo_rolo = 'NOVO' if rolo.status == 'DISPONIVEL' else 'REUTILIZACAO'

            if modo_rolo == 'NOVO' and rolo.status != 'DISPONIVEL':
                raise ValueError('Um novo rolo precisa estar disponível em estoque.')

            if modo_rolo == 'REUTILIZACAO' and rolo.status != 'EM_USO':
                raise ValueError('A reutilização deve selecionar um rolo que já esteja em uso.')

        numero_inicial_utilizado = int(numero_inicial_utilizado)

        if False and lote.quantidade_disponivel <= 0:
            raise ValueError(
                f'O lote {lote.numero_inicial}-{lote.numero_final} não possui rolos disponíveis.'
            )

        ChecklistService._validar_numero_dentro_do_lote(
            lote, numero_inicial_utilizado, 'Número inicial'
        )

        if rolo and numero_inicial_utilizado < rolo.numero_atual:
            raise ValueError(
                f'O número inicial não pode ser menor que o número atual do rolo ({rolo.numero_atual}).'
            )

        # impede duplicidade do mesmo lote no mesmo checklist
        if ChecklistLoteTag.objects.filter(checklist=checklist, rolo=rolo).exists():
            raise ValueError(
                f'O lote {lote.numero_inicial}-{lote.numero_final} já foi adicionado a este checklist.'
            )

        item = ChecklistLoteTag.objects.create(
            checklist=checklist,
            lote=lote,
            rolo=rolo,
            numero_inicial_utilizado=numero_inicial_utilizado,
        )

        if rolo:
            if modo_rolo == 'NOVO':
                if lote.quantidade_disponivel <= 0:
                    raise ValueError(
                        f'O lote {lote.numero_inicial}-{lote.numero_final} não possui rolos novos disponíveis.'
                    )
                lote.quantidade_disponivel -= 1
                lote.save(update_fields=['quantidade_disponivel'])

            rolo.status = 'EM_USO'
            rolo.save(update_fields=['status'])

        HistoricoInsumo.objects.create(
            tipo='CHECKLIST',
            usuario=usuario,
            descricao=f'Lote de TAG adicionado ao checklist {checklist.id}.',
            dados={
                'checklist': checklist.id,
                'inventario': str(checklist.inventario),
                'base': checklist.inventario.base.nome,
                'lote_id': lote.id,
                'lote_faixa': f'{lote.numero_inicial}-{lote.numero_final}',
                'rolo': rolo.codigo if rolo else None,
                'modo_rolo': modo_rolo,
                'numero_inicial_utilizado': numero_inicial_utilizado,
            },
        )

        return item

    @staticmethod
    @transaction.atomic
    def atualizar_retorno_lote_tag(*, item_lote, numero_final_utilizado):
        """
        Usado na finalização/edição do checklist para informar até onde a TAG foi usada.
        """
        numero_final_utilizado = int(numero_final_utilizado)

        ChecklistService._validar_numero_dentro_do_lote(
            item_lote.lote, numero_final_utilizado, 'Número final'
        )

        if numero_final_utilizado < item_lote.numero_inicial_utilizado:
            raise ValueError(
                f'O número final ({numero_final_utilizado}) não pode ser menor que o número inicial '
                f'({item_lote.numero_inicial_utilizado}).'
            )

        item_lote.numero_final_utilizado = numero_final_utilizado
        item_lote.save(update_fields=['numero_final_utilizado'])

        if item_lote.rolo_id:
            rolo = item_lote.rolo
            proximo_numero = numero_final_utilizado + 1
            rolo.numero_atual = min(proximo_numero, item_lote.lote.numero_final)
            rolo.status = (
                'ESGOTADO'
                if numero_final_utilizado >= item_lote.lote.numero_final
                else 'EM_USO'
            )
            rolo.save(update_fields=['numero_atual', 'status'])

        return item_lote

    @staticmethod
    @transaction.atomic
    def atualizar_tags_finalizacao(*, checklist, data):
        """
        Atualiza o número final utilizado de cada lote do checklist.
        Espera campos no POST como:
        - tag_final_item_12 = 4568
        - tag_final_item_13 = 6789
        """
        for item_lote in checklist.lotes_tags_movimentados.select_related('lote'):
            valor = data.get(f'tag_final_item_{item_lote.id}', '').strip()
            if not valor:
                raise ValueError(
                    f'Informe o número final utilizado para o lote '
                    f'{item_lote.lote.numero_inicial}-{item_lote.lote.numero_final}.'
                )

            ChecklistService.atualizar_retorno_lote_tag(
                item_lote=item_lote,
                numero_final_utilizado=int(valor),
            )


    # FINALIZAÇÃO
    @staticmethod
    @transaction.atomic
    def finalizar(*, checklist, usuario):
        if checklist.status == 'FINALIZADO':
            raise ValueError('Checklist já finalizado.')

        base = checklist.inventario.base

        # ==========================================
        # 1. INSUMOS
        # ==========================================
        for item in checklist.itens.select_related('insumo'):
            if item.status_retorno == 'PENDENTE':
                raise ValueError(
                    f'O item "{item.insumo.descricao}" ainda está pendente de conferência.'
                )

            total = (
                item.quantidade_utilizada
                + item.quantidade_retornada
                + item.quantidade_perdida
            )
            if total != item.quantidade_enviada:
                raise ValueError(
                    f'O item "{item.insumo.descricao}" não está conciliado. '
                    f'Enviado: {item.quantidade_enviada}. Apurado: {total}.'
                )

            if item.quantidade_retornada > 0:
                MovimentacaoService.devolucao(
                    base=base,
                    insumo=item.insumo,
                    quantidade=item.quantidade_retornada,
                    usuario=usuario,
                    observacao=f'Retorno do checklist {checklist.id}',
                )

            if item.quantidade_utilizada > 0 or item.quantidade_perdida > 0:
                ConsumoService.gerar(item=item)

        # ==========================================
        # 2. EQUIPAMENTOS
        # ==========================================
        equipamentos_pendentes = checklist.equipamentos_utilizados.filter(status_retorno='PENDENTE')
        if equipamentos_pendentes.exists():
            pendentes = ', '.join([
                f'{e.equipamento.patrimonio} ({e.equipamento.numero_serie})'
                for e in equipamentos_pendentes
            ])
            raise ValueError(
                f'O checklist não pode ser finalizado pois os seguintes equipamentos '
                f'não tiveram o retorno confirmado: {pendentes}'
            )

        for item_equip in checklist.equipamentos_utilizados.select_related('equipamento'):
            equipamento = item_equip.equipamento
            if item_equip.status_retorno == 'RETORNADO':
                equipamento.status = 'ATIVO'
                equipamento.save(update_fields=['status', 'data_atualizacao'])

        # ==========================================
        # 3. TAGS
        # ==========================================
        itens_lote = checklist.lotes_tags_movimentados.select_related('lote')

        for item_lote in itens_lote:
            lote = item_lote.lote

            if item_lote.numero_final_utilizado is None:
                raise ValueError(
                    f'O lote de TAG {lote.numero_inicial}-{lote.numero_final} '
                    f'não teve o número final informado.'
                )

            ChecklistService._validar_numero_dentro_do_lote(
                lote, item_lote.numero_inicial_utilizado, 'Número inicial'
            )
            ChecklistService._validar_numero_dentro_do_lote(
                lote, item_lote.numero_final_utilizado, 'Número final'
            )

            if item_lote.numero_final_utilizado < item_lote.numero_inicial_utilizado:
                raise ValueError(
                    f'O número final do lote {lote.numero_inicial}-{lote.numero_final} '
                    f'não pode ser menor que o número inicial.'
                )

            quantidade_utilizada = ChecklistService._quantidade_tags_utilizadas(
                item_lote.numero_inicial_utilizado,
                item_lote.numero_final_utilizado,
            )

            if quantidade_utilizada < 0:
                raise ValueError(
                    f'A quantidade utilizada do lote {lote.numero_inicial}-{lote.numero_final} é inválida.'
                )

            if False and quantidade_utilizada > lote.quantidade_disponivel:
                raise ValueError(
                    f'O lote {lote.numero_inicial}-{lote.numero_final} não possui saldo suficiente. '
                    f'Disponível: {lote.quantidade_disponivel}. '
                    f'Necessário: {quantidade_utilizada}.'
                )

            # registra a faixa efetivamente utilizada no inventário
            MovimentacaoTag.objects.create(
                inventario=checklist.inventario,
                lote=lote,
                numero_inicial=item_lote.numero_inicial_utilizado,
                numero_final=item_lote.numero_final_utilizado,
                tipo='UTILIZACAO',
                usuario=usuario,
            )

            # baixa saldo apenas quando o consumo real é conhecido
            pass

        # ==========================================
        # 4. HISTÓRICO / FINALIZAÇÃO
        # ==========================================
        HistoricoInsumo.objects.create(
            tipo='CHECKLIST',
            usuario=usuario,
            descricao=f'Checklist do inventário {checklist.inventario} finalizado.',
            dados={
                'checklist': checklist.id,
                'inventario': str(checklist.inventario),
                'cliente': checklist.inventario.cliente.sigla,
                'base': checklist.inventario.base.nome,
                'data_inicio': str(checklist.data_inicio),
                'itens': checklist.itens.count(),
                'equipamentos': checklist.equipamentos_utilizados.count(),
                'lotes_tags': checklist.lotes_tags_movimentados.count(),
            },
        )

        agora = timezone.now()
        checklist.status = 'FINALIZADO'
        checklist.data_fim = agora
        checklist.finalizado_em = agora
        checklist.finalizado_por = usuario
        checklist.save(update_fields=[
            'status', 'data_fim', 'finalizado_em', 'finalizado_por'
        ])

        ComunicadoService.checklist_finalizado(checklist, usuario)

        return checklist


    # PROCESSAMENTO DO FORMULÁRIO
    @staticmethod
    @transaction.atomic
    def processar_checklist(*, checklist, data, usuario):
        payload = ChecklistParserService.parse_post(data)

        # --------------------------
        # INSUMOS
        # --------------------------
        for item in payload["insumos"]:
            insumo = Insumo.objects.get(id=item["insumo_id"])
            ChecklistService.registrar_envio_item(
                checklist=checklist,
                insumo=insumo,
                quantidade_enviada=item["quantidade_enviada"],
                usuario=usuario
            )

        # --------------------------
        # EQUIPAMENTOS
        # --------------------------
        for eq in payload["equipamentos"]:
            equipamento = Equipamento.objects.get(id=eq["id"])
            ChecklistService.adicionar_equipamento(
                checklist=checklist,
                equipamento=equipamento,
                usuario=usuario,
            )

        # --------------------------
        # TAGS
        # --------------------------
        for tag in payload["tags"]:
            lote = LoteTag.objects.get(id=tag["lote_id"])
            ChecklistService.adicionar_lote_tag(
                checklist=checklist,
                lote=lote,
                numero_inicial_utilizado=tag["numero_inicial_utilizado"],
                usuario=usuario,
            )

class ChecklistParserService:

    @staticmethod
    def parse_post(data):
        insumos = []
        equipamentos = []
        tags = []

        # ==========================================
        # INSUMOS
        # ==========================================
        for key, value in data.items():
            if key.startswith("insumo_") and key.endswith("_enviada"):
                insumo_id = key.split("_")[1]
                if value:
                    insumos.append({
                        "insumo_id": int(insumo_id),
                        "quantidade_enviada": Decimal(value),
                        "quantidade_utilizada": Decimal(data.get(f"insumo_{insumo_id}_utilizada", 0)),
                        "quantidade_retornada": Decimal(data.get(f"insumo_{insumo_id}_retornada", 0)),
                        "quantidade_perdida": Decimal(data.get(f"insumo_{insumo_id}_perdida", 0)),
                    })

        # ==========================================
        # EQUIPAMENTOS
        # ==========================================
        for key, value in data.items():
            if key.startswith("equipamentos_"):
                categoria = key.replace("equipamentos_", "")
                if value:
                    equipamentos.append({
                        "id": int(value),
                        "categoria": categoria,
                    })

        # ==========================================
        # TAGS
        # ==========================================
        # Espera campos:
        # lote_tag_1_id
        # tag_numero_inicial_1
        # tag_numero_final_1   (opcional)
        #
        # lote_tag_2_id
        # tag_numero_inicial_2
        # tag_numero_final_2
        # ...
        for key, value in data.items():
            if key.startswith("lote_tag_") and key.endswith("_id"):
                lote_id = value
                if lote_id:
                    idx = key.replace("lote_tag_", "").replace("_id", "")

                    numero_inicial = data.get(f"tag_numero_inicial_{idx}", '').strip()
                    numero_final = data.get(f"tag_numero_final_{idx}", '').strip()

                    if not numero_inicial:
                        raise ValueError('Número inicial da TAG não informado.')

                    tags.append({
                        "lote_id": int(lote_id),
                        "numero_inicial_utilizado": int(numero_inicial),
                        "numero_final_utilizado": int(numero_final) if numero_final else None,
                    })

        return {
            "insumos": insumos,
            "equipamentos": equipamentos,
            "tags": tags,
        }
