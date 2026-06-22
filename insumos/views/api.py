from django.contrib.auth.decorators import login_required
from django.db.models.functions import TruncMonth
from decimal import Decimal
from django.http import JsonResponse
from django.db.models import (Q, Sum, F)
from insumos.models import ConsumoInsumo
from insumos.models import (Inventario, ChecklistDiario, SolicitacaoInsumo, Insumo)
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from insumos.models import Insumo
from insumos.forms import (InsumoForm, CadastroInsumoForm)
from insumos.services.movimentacao_service import MovimentacaoService
from django.http import JsonResponse
from estoque.models import Equipamento, Produto
from insumos.models import LoteTag
from django.db import transaction
from django.utils import timezone
from insumos.models import MovimentacaoTag
import openpyxl
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.dateparse import parse_date
from django.utils.timezone import make_aware
from datetime import datetime
from insumos.models import Inventario, Cliente
from estoque.models import Base, Empresa

@login_required
def estoque_insumos(request):

    perfil = request.user.perfil
    bases = perfil.regionais.all()
    estoque = []

    for base in bases:

        for insumo in Insumo.objects.filter(ativo=True).select_related('categoria'):

            saldo = MovimentacaoService.saldo(base, insumo)

            if saldo <= 0:
                continue

            estoque.append({
                'base': base,
                'insumo': insumo,
                'saldo': saldo,
                'minimo': insumo.estoque_minimo,
                'critico': saldo <= insumo.estoque_minimo
            })

    return render(request, 'insumos/estoque_insumos.html', {'estoque': estoque})

@login_required
def kpi_inventarios(request):

    perfil = request.user.perfil

    qs = Inventario.objects.all()

    if not perfil.is_admin:
        qs = qs.filter(base__in=perfil.regionais.all())

    data = {
        "planejados": qs.filter(status="PLANEJADO").count(),
        "andamento": qs.filter(status="EM_ANDAMENTO").count(),
        "finalizados": qs.filter(status="FINALIZADO").count(),
    }

    return JsonResponse(data)

@login_required
def consumo_por_base(request):

    data = (
        ConsumoInsumo.objects
        .values("inventario__base__nome")
        .annotate(total=Sum("valor_total"))
        .order_by("-total")
    )

    return JsonResponse(list(data), safe=False)

@login_required
def ranking_insumos(request):

    data = (
        ConsumoInsumo.objects
        .values("insumo__descricao")
        .annotate(total=Sum("quantidade"))
        .order_by("-total")[:10]
    )

    return JsonResponse(list(data), safe=False)

@login_required
def consumo_por_mes(request):

    data = (
        ConsumoInsumo.objects
        .annotate(mes=TruncMonth("criado_em"))
        .values("mes")
        .annotate(total=Sum("valor_total"))
        .order_by("mes")
    )

    return JsonResponse(list(data), safe=False)

@login_required
def lista_insumos(request):

    insumos = Insumo.objects.select_related('categoria').order_by(
        'categoria__nome',
        'descricao'
    )

    categoria = request.GET.get('categoria')

    if categoria:
        insumos = insumos.filter(categoria_id=categoria)

    return render(request, 'insumos/lista_insumos.html', {
        'insumos': insumos
    })

@login_required
def cadastrar_insumo(request):

    if request.method == 'POST':

        form = CadastroInsumoForm(request.POST, user=request.user)

        if form.is_valid():

            base = form.cleaned_data['base']
            insumo = form.cleaned_data['insumo']
            quantidade = form.cleaned_data['quantidade']

            MovimentacaoService.entrada(
                base=base,
                insumo=insumo,
                quantidade=quantidade,
                usuario=request.user,
                valor_unitario=Decimal('0.00'),
                observacao='Cadastro inicial de estoque'
            )

            messages.success(request, 'Entrada registrada com sucesso.')

            return redirect('insumos:cadastrar_insumos')

    else:

        form = CadastroInsumoForm(user=request.user)

    return render(request, 'insumos/cadastrar_insumos.html', {'form': form})

def get_equipamentos_disponiveis(request, categoria):

    regionais_ids = request.user.perfil.regionais_ids

    if request.user.perfil.is_admin:
        equipamentos = Equipamento.objects.filter(status='ATIVO', produto__categoria=categoria)
    else:
        equipamentos = Equipamento.objects.filter(status='ATIVO', produto__categoria=categoria, regional_id__in=regionais_ids)

    data = [{
        'id': eq.id,
        'text': f"{eq.numero_serie} - {eq.produto.descricao} - {eq.patrimonio}",
        'numero_serie': eq.numero_serie,
        'patrimonio': eq.patrimonio
    } for eq in equipamentos]

    return JsonResponse({'results': data})

def get_lotes_tags_disponiveis(request):

    regionais_ids = request.user.perfil.regionais_ids

    if request.user.perfil.is_admin:
        lotes = LoteTag.objects.filter(ativo=True, quantidade_disponivel__gt=0)
    else:
        lotes = LoteTag.objects.filter(ativo=True, quantidade_disponivel__gt=0, base_id__in=regionais_ids)

    data = [{
        'id': lote.id,
        'text': f"{lote.base.nome} - Lote {lote.numero_inicial} a {lote.numero_final} (Disponíveis: {lote.quantidade_disponivel})",
        'numero_inicial': lote.numero_inicial,
        'numero_final': lote.numero_final,
        'quantidade_disponivel': lote.quantidade_disponivel
    } for lote in lotes]

    return JsonResponse({'results': data})

@login_required
def editar_insumo(request, pk):

    insumo = get_object_or_404(Insumo, pk=pk)

    if request.method == 'POST':
        form = InsumoForm(request.POST, instance=insumo)

        if form.is_valid():
            form.save()
            messages.success(request, 'Insumo atualizado com sucesso.')
            return redirect('insumos:lista_insumos')

    else:
        form = InsumoForm(instance=insumo)

    return render(
        request,
        'insumos/cadastrar_insumo.html',
        {
            'form': form,
            'insumo': insumo
        }
    )

@login_required
def insumos_por_categoria(request):

    categoria_id = request.GET.get('categoria')

    if not categoria_id:
        return JsonResponse({'insumos': []})

    insumos = (Insumo.objects.filter(categoria_id=categoria_id, ativo=True).order_by('descricao').values('id', 'descricao'))

    return JsonResponse({'insumos': list(insumos)})

def finalizar_checklist(checklist_id, usuario):
    checklist = ChecklistDiario.objects.get(id=checklist_id)

    with transaction.atomic():
        for item_equip in checklist.equipamentos_utilizados.all():
            equip = item_equip.equipamento

            if item_equip.tag_volta:
                item_equip.data_retorno = timezone.now()
                item_equip.save()
                equip.status = 'ATIVO'
                equip.save()
            else:
                equip.status = 'EM_USO'
                equip.save()

        for item_lote in checklist.lotes_tags_movimentados.all():
            lote = item_lote.lote
            MovimentacaoTag.objects.create(
                inventario=checklist.inventario,
                lote=lote,
                numero_inicial=item_lote.numero_inicial_enviado,
                numero_final=item_lote.numero_final_enviado,
                tipo='ENVIO',
                usuario=usuario
            )

            if item_lote.numero_inicial_retornado and item_lote.numero_final_retornado:
                MovimentacaoTag.objects.create(
                    inventario=checklist.inventario,
                    lote=lote,
                    numero_inicial=item_lote.numero_inicial_retornado,
                    numero_final=item_lote.numero_final_retornado,
                    tipo='RETORNO',
                    usuario=usuario
                )

                item_lote.status = 'RETORNADO'
                item_lote.save()

        checklist.status = 'FINALIZADO'
        checklist.finalizado_em = timezone.now()
        checklist.finalizado_por = usuario
        checklist.save()

def checklist_list(request):
    checklists = ChecklistDiario.objects.all()
    return render(request, 'insumos/checklist_list.html', {'checklists': checklists})

@staff_member_required
def importar_excel(request):
    if request.method == 'POST' and request.FILES.get('arquivo'):
        arquivo = request.FILES['arquivo']
        try:
            wb = openpyxl.load_workbook(arquivo, data_only=True)
        except Exception as e:
            messages.error(request, f'Erro ao ler o arquivo: {e}')
            return redirect('insumos:importar_excel')

        # Mapeamento de regionais do Excel para nomes no banco
        REGIONAL_MAP = {
            'SP LESTE X': 'OXXO SP LESTE X',
            'SP SUL X': 'OXXO SP SUL X',
            'SP LITORAL X': 'OXXO SP LITORAL X',
            'SP INT CPN X': 'OXXO SP INT CPN X',
            'SP INT CPN ': 'SP INT CPN',
            'SP INT JUNDIAÍ X': 'OXXO SP INT JUNDIAÍ X',
            'SP INT PIRACICABA X': 'OXXO SP INT PIRACICABA X',
            'SP INT SOROCABA X': 'OXXO SP INT SOROCABA X',
            'SP INT VALE X': 'OXXO SP INT VALE X',
            'SP LESTE GRU X': 'OXXO SP LESTE GRU X',
            'SP LESTE AND X': 'OXXO SP LESTE AND X',
            'PR PARANAGUÁ': 'PR PARANAGUÁ',
            'SP INT STA ISA': 'SP INT STA ISABEL',
            'SP LESTE ITAQUA': 'SP LESTE ITAQUA',
            'RJ': 'RIO DE JANEIRO',
            'PR CURITIBA': 'PR CURITIBA',
            'PR MARINGÁ': 'PR MARINGÁ',
            'PR LONDRINA': 'PR LONDRINA',
            'SC FLORIPA': 'SC FLORIPA',
            'PORTO ALEGRE': 'PORTO ALEGRE',
            'SP SUL': 'SÃO PAULO',
            'SP LESTE': 'SÃO PAULO'
        }

        empresa = Empresa.objects.first()
        if not empresa:
            messages.error(request, 'Nenhuma empresa cadastrada. Crie uma empresa primeiro.')
            return redirect('insumos:importar_excel')

        ABAS_IGNORADAS = ['Siglas e Tipos', 'Alterações']

        with transaction.atomic():
            # 1. Processar aba "Siglas e Tipos" → Clientes
            if 'Siglas e Tipos' in wb.sheetnames:
                sheet = wb['Siglas e Tipos']
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    sigla, nome, segmento, status = row[0], row[1], row[2], row[3]
                    if sigla and nome:
                        Cliente.objects.update_or_create(
                            sigla=sigla,
                            defaults={'nome': nome, 'ativo': status == 'ATIVO'}
                        )
                messages.success(request, 'Clientes importados/atualizados com sucesso.')

            abas_inventario = [nome for nome in wb.sheetnames if nome not in ABAS_IGNORADAS]
            if not abas_inventario:
                messages.warning(request, 'Nenhuma aba de inventário encontrada.')
                return redirect('insumos:importar_excel')

            for aba_nome in abas_inventario:
                sheet = wb[aba_nome]
                messages.info(request, f'Processando aba: {aba_nome}')

                cabecalho = None
                for row_idx, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                    if row and len(row) > 1 and row[1] == 'SIGLA':
                        cabecalho = row_idx
                        break

                if not cabecalho:
                    messages.warning(request, f'Cabeçalho não encontrado na aba "{aba_nome}". Pulando.')
                    continue

                header_row = list(sheet.iter_rows(min_row=cabecalho, max_row=cabecalho, values_only=True))[0]
                col_map = {}
                for idx, col_name in enumerate(header_row):
                    if col_name == 'SIGLA':
                        col_map['sigla'] = idx
                    elif col_name == 'Nº DA LOJA':
                        col_map['loja'] = idx
                    elif col_name == 'DATA':
                        col_map['data'] = idx
                    elif col_name == 'ENDEREÇO':
                        col_map['endereco'] = idx
                    elif col_name == 'BAIRRO/NOME DA LOJA':
                        col_map['bairro'] = idx
                    elif col_name == 'CIDADE':
                        col_map['cidade'] = idx
                    elif col_name == 'REGIONAL':
                        col_map['regional'] = idx

                colunas_obrigatorias = ['sigla', 'loja', 'data', 'regional']
                if not all(key in col_map for key in colunas_obrigatorias):
                    messages.warning(request, f'Aba "{aba_nome}" não possui todas as colunas necessárias. Pulando.')
                    continue

                contador = 0
                for row in sheet.iter_rows(min_row=cabecalho + 1, values_only=True):
                    if not row or not any(row):
                        continue

                    sigla = row[col_map['sigla']] if col_map.get('sigla') is not None and len(row) > col_map['sigla'] else None
                    loja = row[col_map['loja']] if col_map.get('loja') is not None and len(row) > col_map['loja'] else None
                    data_str = row[col_map['data']] if col_map.get('data') is not None and len(row) > col_map['data'] else None
                    endereco = row[col_map['endereco']] if col_map.get('endereco') is not None and len(row) > col_map['endereco'] else ''
                    bairro = row[col_map['bairro']] if col_map.get('bairro') is not None and len(row) > col_map['bairro'] else ''
                    cidade = row[col_map['cidade']] if col_map.get('cidade') is not None and len(row) > col_map['cidade'] else ''
                    regional_nome = row[col_map['regional']] if col_map.get('regional') is not None and len(row) > col_map['regional'] else None

                    if not sigla or not loja or not data_str or not regional_nome:
                        continue

                    # Buscar cliente
                    try:
                        cliente = Cliente.objects.get(sigla=sigla)
                    except Cliente.DoesNotExist:
                        messages.warning(request, f'Cliente {sigla} não encontrado. Linha ignorada.')
                        continue

                    nome_base = REGIONAL_MAP.get(regional_nome, regional_nome)
                    base, created = Base.objects.get_or_create(
                        nome=nome_base,
                        empresa=empresa,
                        defaults={'nome': nome_base, 'grupo_regional': None}
                    )
                    if created:
                        messages.info(request, f'Regional "{nome_base}" criada automaticamente.')

                    if isinstance(data_str, datetime):
                        data_inicio = data_str.date()
                    else:
                        data_inicio = parse_date(str(data_str)) if data_str else None
                    if not data_inicio:
                        messages.warning(request, f'Data inválida para {sigla} {loja}. Linha ignorada.')
                        continue

                    # Criar inventário COM os campos de endereço
                    inventario, created = Inventario.objects.get_or_create(
                        cliente=cliente,
                        loja=str(loja),
                        base=base,
                        data_inicio=data_inicio,
                        defaults={
                            'status': 'PLANEJADO',
                            'criado_por': request.user,
                            'endereco': endereco,
                            'bairro': bairro,
                            'cidade': cidade,
                        }
                    )
                    if not created:
                        # Atualiza os campos caso o inventário já exista
                        inventario.endereco = endereco
                        inventario.bairro = bairro
                        inventario.cidade = cidade
                        inventario.save()
                        messages.info(request, f'Inventário atualizado: {cliente.sigla} - Loja {loja} - {data_inicio}')
                    else:
                        contador += 1
                        messages.success(request, f'Inventário criado: {cliente.sigla} - Loja {loja} - {data_inicio}')

                messages.success(request, f'Aba "{aba_nome}" processada: {contador} inventários criados.')

            messages.success(request, 'Importação concluída!')
            return redirect('insumos:importar_excel')

    return render(request, 'insumos/importar_excel.html')

@login_required
def inventario_detalhes(request, inventario_id):
    inventario = get_object_or_404(Inventario, pk=inventario_id)
    data = {
        'cliente': f"{inventario.cliente.sigla} - {inventario.cliente.nome}",
        'sigla': inventario.cliente.sigla,
        'loja': inventario.loja,
        'data': inventario.data_inicio.strftime('%d/%m/%Y'),
        'endereco': inventario.endereco or '',
        'bairro': inventario.bairro or '',
        'cidade': inventario.cidade or '',
    }
    return JsonResponse(data)