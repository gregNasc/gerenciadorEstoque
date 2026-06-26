from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from insumos.models import (ChecklistDiario, ChecklistEquipamento, ChecklistLoteTag, HistoricoInsumo, ItemChecklist, MovimentacaoTag, LoteTag, Insumo)
from insumos.services.consumo_service import ConsumoService
from insumos.services.movimentacao_service import MovimentacaoService
from estoque.models import Equipamento

class ChecklistService:

    @staticmethod
    @transaction.atomic
    def criar(*, inventario, usuario, responsavel=None, observacao=''):
        return ChecklistDiario.objects.create(
            inventario=inventario,
            data_inicio=timezone.now(),
            criado_por=usuario,
            responsavel=responsavel or usuario,
            observacao=observacao,
            status='ABERTO',
        )

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
            raise ValueError('Este insumo ja foi adicionado ao checklist.')

        return item

    @staticmethod
    @transaction.atomic
    def registrar_envio_item(*, checklist, insumo, quantidade_enviada, usuario):
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
    @transaction.atomic
    def adicionar_equipamento(*, checklist, equipamento, usuario, tag_saida='', tag_volta=''):
        if equipamento.regional_id != checklist.inventario.base_id:
            raise ValueError(
                f'O equipamento {equipamento} nao pertence a base do inventario.'
            )

        if equipamento.status != 'ATIVO':
            raise ValueError(
                f'O equipamento {equipamento} nao esta ativo para envio.'
            )

        item = ChecklistEquipamento.objects.create(
            checklist=checklist,
            equipamento=equipamento,
            tag_saida=tag_saida or equipamento.patrimonio or equipamento.numero_serie,
            tag_volta=tag_volta or '',
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
    @transaction.atomic
    def adicionar_lote_tag(*, checklist, lote, numero_inicial_enviado, numero_final_enviado, usuario, numero_inicial_retornado=None, numero_final_retornado=None,):
        if lote.base_id != checklist.inventario.base_id:
            raise ValueError('O lote de tags nao pertence a base do inventario.')

        numero_inicial_enviado = int(numero_inicial_enviado)
        numero_final_enviado = int(numero_final_enviado)

        if numero_inicial_enviado > numero_final_enviado:
            raise ValueError('A faixa inicial de tags nao pode ser maior que a final.')

        quantidade_enviada = numero_final_enviado - numero_inicial_enviado + 1

        if lote.quantidade_disponivel < quantidade_enviada:
            raise ValueError('Lote de tags sem saldo disponivel para esta faixa.')

        item = ChecklistLoteTag.objects.create(
            checklist=checklist,
            lote=lote,
            numero_inicial_enviado=numero_inicial_enviado,
            numero_final_enviado=numero_final_enviado,
            numero_inicial_retornado=numero_inicial_retornado,
            numero_final_retornado=numero_final_retornado,
        )

        MovimentacaoTag.objects.create(
            inventario=checklist.inventario,
            lote=lote,
            numero_inicial=numero_inicial_enviado,
            numero_final=numero_final_enviado,
            tipo='ENVIO',
            usuario=usuario,
        )

        lote.quantidade_disponivel -= quantidade_enviada
        lote.save(update_fields=['quantidade_disponivel'])

        return item

    @staticmethod
    @transaction.atomic
    def atualizar_item(*, item, utilizada, retornada, perdida):
        utilizada = Decimal(str(utilizada or '0'))
        retornada = Decimal(str(retornada or '0'))
        perdida = Decimal(str(perdida or '0'))
        total = utilizada + retornada + perdida

        if total > item.quantidade_enviada:
            raise ValueError('A soma nao pode exceder a quantidade enviada.')

        item.quantidade_utilizada = utilizada
        item.quantidade_retornada = retornada
        item.quantidade_perdida = perdida
        item.save(
            update_fields=[
                'quantidade_utilizada',
                'quantidade_retornada',
                'quantidade_perdida',
            ]
        )

        return item

    @staticmethod
    @transaction.atomic
    def finalizar(*, checklist, usuario):
        if checklist.status == 'FINALIZADO':
            raise ValueError('Checklist ja finalizado.')

        base = checklist.inventario.base

        for item in checklist.itens.select_related('insumo'):
            total = (
                item.quantidade_utilizada
                + item.quantidade_retornada
                + item.quantidade_perdida
            )

            if total != item.quantidade_enviada:
                raise ValueError(
                    f'O item "{item.insumo.descricao}" nao esta conciliado. '
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

            if item.quantidade_utilizada > 0:
                ConsumoService.gerar(item=item)

        for item_equipamento in checklist.equipamentos_utilizados.select_related('equipamento'):
            equipamento = item_equipamento.equipamento

            if item_equipamento.tag_volta:
                item_equipamento.data_retorno = timezone.now()
                item_equipamento.save(update_fields=['data_retorno'])
                equipamento.status = 'ATIVO'
                equipamento.save(update_fields=['status', 'data_atualizacao'])

        HistoricoInsumo.objects.create(
            tipo='CHECKLIST',
            usuario=usuario,
            descricao=f'Checklist diario do inventario {checklist.inventario} finalizado.',
            dados={
                'checklist': checklist.id,
                'inventario': str(checklist.inventario),
                'cliente': checklist.inventario.cliente.sigla,
                'base': checklist.inventario.base.nome,
                'data_inicio': str(checklist.data_inicio),
                'itens': checklist.itens.count(),
                'equipamentos': checklist.equipamentos_utilizados.count(),
            },
        )

        agora = timezone.now()
        checklist.status = 'FINALIZADO'
        checklist.data_fim = agora
        checklist.finalizado_em = agora
        checklist.finalizado_por = usuario
        checklist.save(
            update_fields=[
                'status',
                'data_fim',
                'finalizado_em',
                'finalizado_por',
            ]
        )

        return checklist

    @staticmethod
    @transaction.atomic
    def processar_checklist(*, checklist, data, usuario):

        payload = ChecklistParserService.parse_post(data)

        # INSUMOS
        for item in payload["insumos"]:
            insumo = Insumo.objects.get(id=item["insumo_id"])

            ChecklistService.registrar_envio_item(checklist=checklist, insumo=insumo, quantidade_enviada=item["quantidade"], usuario=usuario)

        # EQUIPAMENTOS
        for eq in payload["equipamentos"]:
            equipamento = Equipamento.objects.get(id=eq["id"])

            ChecklistService.adicionar_equipamento(checklist=checklist, equipamento=equipamento, usuario=usuario)

        # TAGS
        for tag in payload["tags"]:
            if tag["saida"]:
                ChecklistService.adicionar_lote_tag(
                    checklist=checklist,
                    lote=LoteTag.objects.first(),
                    numero_inicial_enviado=int(tag["saida"]),
                    numero_final_enviado=int(tag["saida"]),
                    usuario=usuario,
                    numero_inicial_retornado=tag["volta"]
                )

class ChecklistParserService:

    @staticmethod
    def parse_post(data):
        insumos = []
        equipamentos = []
        tags = []

        for key, value in data.items():

            # INSUMOS
            if key.startswith("insumo_") and key.endswith("_enviada"):
                insumo_id = key.split("_")[1]
                if value:
                    insumos.append({"insumo_id": int(insumo_id), "quantidade": Decimal(value)})

            # TAGS
            if key.startswith("tag_saida_"):
                idx = key.replace("tag_saida_", "")
                tags.append({"index": idx, "saida": value, "volta": data.get(f"tag_volta_{idx}")})

            # EQUIPAMENTOS
            if key.startswith("equipamentos_"):
                categoria = key.replace("equipamentos_", "")
                equipamentos.append({"categoria": categoria, "id": int(value)})

        return {"insumos": insumos, "equipamentos": equipamentos, "tags": tags}
