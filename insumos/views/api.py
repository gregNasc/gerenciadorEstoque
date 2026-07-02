from django.db.models.functions import TruncMonth
from django.db.models import (Q, Sum, F)
from django.http import HttpResponse
from insumos.models import ConsumoInsumo
from insumos.models import (Inventario, ChecklistDiario, SolicitacaoInsumo, Insumo)
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from insumos.models import Insumo
from insumos.forms import (InsumoForm, CadastroInsumoForm)
from insumos.services.movimentacao_service import MovimentacaoService
from decimal import Decimal
from django.http import JsonResponse
from estoque.models import Equipamento, Produto
from insumos.models import LoteTag, RoloTag
from insumos.forms import FiltroEstoqueInsumoForm, InventarioForm
from django.db import transaction
from django.utils import timezone
from estoque.decorators import role_required
import openpyxl
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.dateparse import parse_date
from django.utils.timezone import make_aware
from datetime import datetime, date, time
from insumos.models import Inventario, Cliente
from estoque.models import Base, Empresa
from insumos.services.checklist_service import ChecklistService

@login_required
@role_required('admin', 'gestor', 'operador')
def estoque_insumos(request):

    perfil = request.user.perfil
    bases = Base.objects.all() if perfil.is_admin else perfil.regionais.all()
    categoria_id = request.GET.get('categoria')
    insumo_id = request.GET.get('insumo')
    insumos = (Insumo.objects.filter(ativo=True).select_related('categoria'))

    if categoria_id:
        insumos = insumos.filter(categoria_id=categoria_id)

    if insumo_id:
        insumos = insumos.filter(id=insumo_id)

    estoque = []

    for base in bases:

        for insumo in insumos:
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

    form = FiltroEstoqueInsumoForm(request.GET or None)

    return render(
        request,
        'insumos/estoque_insumos.html',
        {
            'estoque': estoque,
            'form': form,
        }
    )

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

    return render(request,'insumos/cadastrar_insumo.html',
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

def finalizar_checklist_legado(checklist_id, usuario):
    checklist = ChecklistDiario.objects.get(id=checklist_id)

    with transaction.atomic():
        ChecklistService.finalizar(checklist=checklist, usuario=usuario)

def checklist_list(request):
    checklists = ChecklistDiario.objects.all()
    return render(request, 'insumos/checklist_list.html', {'checklists': checklists})

def serializar_valor(valor):
    """Converte objetos time, datetime, date para string serializável."""
    if isinstance(valor, time):
        return valor.strftime('%H:%M:%S')
    elif isinstance(valor, (datetime, date)):
        return valor.isoformat()
    elif isinstance(valor, Decimal):
        return float(valor)
    return valor

@staff_member_required
def importar_excel(request):
    if request.method == 'POST' and request.FILES.get('arquivo'):
        arquivo = request.FILES['arquivo']
        try:
            wb = openpyxl.load_workbook(arquivo, data_only=True)
        except Exception as e:
            messages.error(request, f'Erro ao ler o arquivo: {e}')
            return redirect('insumos:importar_excel')

        REGIONAL_MAP = {
            'PORTO ALEGRE': 'PORTO ALEGRE',
            'PR CURITIBA': 'PR CURITIBA',
            'PR MARINGÁ': 'PR MARINGÁ',
            'PR LONDRINA': 'PR LONDRINA',
            'PR PARANAGUÁ': 'PR PARANAGUÁ',
            'SC FLORIPA': 'SC FLORIPA',
            'SP INT CPN': 'SP INT CPN',
            'SP INT LIMEIRA': 'SP INT LIMEIRA',
            'SP INT BAURU': 'SP INT BAURU',
            'SP INT RIBEIRÃO': 'SP INT RIBEIRÃO',
            'SP INT STA ISA': 'SP INT STA ISABEL',
            'SP LESTE ITAQUA': 'SP LESTE ITAQUA',
            'SP LESTE': 'SÃO PAULO',
            'SP SUL': 'SÃO PAULO',
            'RJ': 'RIO DE JANEIRO',
            'SP LESTE X': 'OXXO SP LESTE X',
            'SP SUL X': 'OXXO SP SUL X',
            'SP LITORAL X': 'OXXO SP LITORAL X',
            'SP INT CPN X': 'OXXO SP INT CPN X',
            'SP INT JUNDIAÍ X': 'OXXO SP INT JUNDIAI X',
            'SP INT PIRACICABA X': 'OXXO SP INT PIRACICABA X',
            'SP INT SOROCABA X': 'OXXO SP INT SOROCABA X',
            'SP INT VALE X': 'OXXO SP INT VALE X',
            'SP LESTE GRU X': 'OXXO SP LESTE GRU X',
            'SP LESTE AND X': 'OXXO SP LESTE AND X',
        }

        # Mapeamento das colunas do Excel para os campos do modelo
        COLUMN_MAP = {
            'TIPO': 'tipo',
            'PESSOAS': 'pessoas',
            'OBSERVAÇÃO': 'observacao',
            'LÍDER': 'lider',
            'PONTO DE ENCONTRO': 'ponto_encontro',
            'HORÁRIO DO PONTO DE ENCONTRO': 'horario_ponto',
            'HORÁRIO DE INÍCIO': 'horario_inicio',
            'TIPO DA VISITA': 'tipo_visita',
            'RESPONSÁVEL PELA VISITA': 'responsavel_visita',
            'DATA DA VISITA': 'data_visita',
            'HORÁRIO DA VISITA': 'horario_visita',
            'RELATÓRIO DE VISITA': 'relatorio_visita',
            'PREP': 'prep',
            'HISTÓRICO EQUIPE': 'historico_equipe',
            'HISTÓRICO PEÇAS': 'historico_pecas',
            'HISTÓRICO SATISFAÇÃO': 'historico_satisfacao',
            'HISTÓRICO PREPARAÇÃO': 'historico_preparacao',
            'HISTÓRICO LÍDER': 'historico_lider',
            'HISTÓRICO DATA': 'historico_data',
            'EQUIPE PLAN': 'equipe_plan',
            'PREVISÃO DE PEÇAS': 'previsao_pecas',
            'PROD MÉDIA': 'prod_media',
            'BID': 'bid',
            'CNPJ': 'cnpj',
            'CEP': 'cep',
            'ENVIO DA ESCALA': 'envio_escala',
            'CHAVE': 'chave',
        }

        empresa = Empresa.objects.first()
        if not empresa:
            messages.error(request, 'Nenhuma empresa cadastrada.')
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

            # 2. Processar abas de inventário
            abas_inventario = [nome for nome in wb.sheetnames if nome not in ABAS_IGNORADAS]
            if not abas_inventario:
                messages.warning(request, 'Nenhuma aba de inventário encontrada.')
                return redirect('insumos:importar_excel')

            for aba_nome in abas_inventario:
                sheet = wb[aba_nome]
                messages.info(request, f'Processando aba: {aba_nome}')

                # Encontrar linha de cabeçalho (SIGLA na coluna B)
                cabecalho = None
                for row_idx, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                    if row and len(row) > 1 and row[1] == 'SIGLA':
                        cabecalho = row_idx
                        break

                if not cabecalho:
                    messages.warning(request, f'Cabeçalho não encontrado na aba "{aba_nome}". Pulando.')
                    continue

                header_row = list(sheet.iter_rows(min_row=cabecalho, max_row=cabecalho, values_only=True))[0]

                # Mapear índices das colunas obrigatórias
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
                    messages.warning(request, f'Aba "{aba_nome}" não possui colunas obrigatórias.')
                    continue

                contador = 0
                for row in sheet.iter_rows(min_row=cabecalho + 1, values_only=True):
                    if not row or not any(row):
                        continue

                    # --- Capturar campos obrigatórios ---
                    sigla = row[col_map['sigla']] if col_map.get('sigla') is not None and len(row) > col_map[
                        'sigla'] else None
                    loja = row[col_map['loja']] if col_map.get('loja') is not None and len(row) > col_map[
                        'loja'] else None
                    data_str = row[col_map['data']] if col_map.get('data') is not None and len(row) > col_map[
                        'data'] else None
                    endereco = row[col_map['endereco']] if col_map.get('endereco') is not None and len(row) > col_map[
                        'endereco'] else ''
                    bairro = row[col_map['bairro']] if col_map.get('bairro') is not None and len(row) > col_map[
                        'bairro'] else ''
                    cidade = row[col_map['cidade']] if col_map.get('cidade') is not None and len(row) > col_map[
                        'cidade'] else ''
                    regional_nome = row[col_map['regional']] if col_map.get('regional') is not None and len(row) > \
                                                                col_map['regional'] else None

                    if not sigla or not loja or not data_str or not regional_nome:
                        continue

                    # --- Capturar TODAS as colunas (incluindo as extras) ---
                    dados_completos = {}
                    for idx, valor in enumerate(row):
                        if idx < len(header_row):
                            nome_coluna = header_row[idx]
                        else:
                            nome_coluna = f"col_{idx}"
                        if valor is not None:
                            dados_completos[nome_coluna] = serializar_valor(valor)

                    # Remover colunas que já extraímos (para não duplicar)
                    colunas_extraidas = ['SIGLA', 'Nº DA LOJA', 'DATA', 'ENDEREÇO', 'BAIRRO/NOME DA LOJA', 'CIDADE',
                                         'REGIONAL']
                    for col in colunas_extraidas:
                        dados_completos.pop(col, None)

                    # --- Buscar cliente ---
                    try:
                        cliente = Cliente.objects.get(sigla=sigla)
                    except Cliente.DoesNotExist:
                        messages.warning(request, f'Cliente {sigla} não encontrado.')
                        continue

                    # --- Mapear regional ---
                    nome_base = REGIONAL_MAP.get(regional_nome, regional_nome)
                    base, created = Base.objects.get_or_create(
                        nome=nome_base,
                        empresa=empresa,
                        defaults={'nome': nome_base, 'grupo_regional': None}
                    )
                    if created:
                        messages.info(request, f'Regional "{nome_base}" criada.')

                    # --- Converter data ---
                    if isinstance(data_str, datetime):
                        data_inicio = data_str.date()
                    else:
                        data_inicio = parse_date(str(data_str)) if data_str else None
                    if not data_inicio:
                        messages.warning(request, f'Data inválida para {sigla} {loja}.')
                        continue

                    # --- Preparar defaults com campos extras ---
                    defaults = {
                        'status': 'PLANEJADO',
                        'criado_por': request.user,
                        'endereco': endereco,
                        'bairro': bairro,
                        'cidade': cidade,
                        'dados_brutos': dados_completos,
                    }

                    # --- Mapear colunas extras para os campos do modelo ---
                    for excel_col, model_field in COLUMN_MAP.items():
                        valor = dados_completos.get(excel_col)
                        if valor is not None and str(valor).strip():
                            # Conversão de tipos
                            if model_field in ['pessoas', 'equipe_plan', 'previsao_pecas']:
                                try:
                                    valor = int(float(valor))
                                except (ValueError, TypeError):
                                    valor = None
                            elif model_field in ['prep', 'prod_media']:
                                try:
                                    valor = float(valor)
                                except (ValueError, TypeError):
                                    valor = None
                            elif model_field in ['horario_ponto', 'horario_inicio', 'horario_visita']:
                                if isinstance(valor, time):
                                    pass  # já é time
                                else:
                                    try:
                                        if isinstance(valor, str) and ':' in valor:
                                            valor = datetime.strptime(valor, '%H:%M:%S').time()
                                        else:
                                            valor = None
                                    except:
                                        valor = None
                            elif model_field in ['data_visita', 'historico_data', 'envio_escala']:
                                if isinstance(valor, datetime):
                                    valor = valor.date()
                                else:
                                    try:
                                        valor = parse_date(str(valor))
                                    except:
                                        valor = None
                            defaults[model_field] = valor

                    # --- Criar ou atualizar inventário ---
                    inventario, created = Inventario.objects.get_or_create(
                        cliente=cliente,
                        loja=str(loja),
                        base=base,
                        data_inicio=data_inicio,
                        defaults=defaults
                    )
                    if not created:
                        for key, value in defaults.items():
                            setattr(inventario, key, value)
                        inventario.save()
                        messages.info(request, f'Inventário atualizado: {cliente.sigla} - Loja {loja}')
                    else:
                        contador += 1
                        messages.success(request, f'Inventário criado: {cliente.sigla} - Loja {loja}')

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

def media_pecas_por_cliente(request):

    inventarios = Inventario.objects.filter(status='FINALIZADO')

    total = 0
    count = 0
    for inv in inventarios:
        previsao = inv.dados_brutos.get('PREVISÃO DE PEÇAS')
        if previsao and isinstance(previsao, (int, float)):
            total += previsao
            count += 1

    media = total / count if count > 0 else 0
    return JsonResponse({'media_pecas': media})

def planejamento_inventarios(request):
    inventarios = Inventario.objects.filter(status='PLANEJADO')
    dados = []
    for inv in inventarios:
        dados.append({
            'cliente': inv.cliente.sigla,
            'loja': inv.loja,
            'data': inv.data_inicio,
            'tipo': inv.dados_brutos.get('TIPO'),
            'pessoas': inv.dados_brutos.get('PESSOAS'),
            'lider': inv.dados_brutos.get('LÍDER'),
            'previsao_pecas': inv.dados_brutos.get('PREVISÃO DE PEÇAS'),
            'prod_media': inv.dados_brutos.get('PROD MÉDIA'),
            'observacao': inv.dados_brutos.get('OBSERVAÇÃO'),
        })
    return render(request, 'planejamento.html', {'inventarios': dados})

@login_required
def gerenciar_inventarios(request):
    if not request.user.perfil.is_admin:
        messages.error(request, 'Acesso restrito a administradores.')
        return redirect('estoque:index')

    # Filtros
    cliente_id = request.GET.get('cliente')
    regional_id = request.GET.get('regional')
    status_filter = request.GET.get('status')
    data_inicio = request.GET.get('data_inicio')
    data_fim = request.GET.get('data_fim')

    inventarios = Inventario.objects.select_related('cliente', 'base', 'criado_por').all()

    if cliente_id:
        inventarios = inventarios.filter(cliente_id=cliente_id)
    if regional_id:
        inventarios = inventarios.filter(base_id=regional_id)
    if status_filter:
        inventarios = inventarios.filter(status=status_filter)
    if data_inicio:
        inventarios = inventarios.filter(data_inicio__gte=data_inicio)
    if data_fim:
        inventarios = inventarios.filter(data_inicio__lte=data_fim)

    inventarios = inventarios.order_by('-data_inicio')

    context = {
        'inventarios': inventarios,
        'clientes': Cliente.objects.filter(ativo=True).order_by('sigla'),
        'regionais': Base.objects.all().order_by('nome'),
        'status_choices': Inventario.STATUS,
        'filtro_cliente': cliente_id,
        'filtro_regional': regional_id,
        'filtro_status': status_filter,
        'filtro_data_inicio': data_inicio,
        'filtro_data_fim': data_fim,
    }
    return render(request, 'insumos/gerenciar_inventarios.html', context)

@login_required
def lista_inventarios(request):
    # Filtros via GET
    sigla = request.GET.get('sigla', '')
    loja = request.GET.get('loja', '')
    data_inicio = request.GET.get('data_inicio', '')
    data_fim = request.GET.get('data_fim', '')
    regional_id = request.GET.get('regional', '')

    # Base queryset com permissões do usuário
    if request.user.perfil.is_admin:
        inventarios = Inventario.objects.all().select_related('cliente', 'base')
    else:
        inventarios = Inventario.objects.filter(
            base__in=request.user.perfil.regionais.all()
        ).select_related('cliente', 'base')

    # Aplicar filtros
    if sigla:
        inventarios = inventarios.filter(cliente__sigla__icontains=sigla)
    if loja:
        inventarios = inventarios.filter(loja__icontains=loja)
    if data_inicio:
        inventarios = inventarios.filter(data_inicio__gte=data_inicio)
    if data_fim:
        inventarios = inventarios.filter(data_inicio__lte=data_fim)
    if regional_id:
        inventarios = inventarios.filter(base_id=regional_id)

    # Ordenar por data mais recente
    inventarios = inventarios.order_by('-data_inicio')

    # Lista de regionais para o filtro
    if request.user.perfil.is_admin:
        regionais = Base.objects.all().order_by('nome')
    else:
        regionais = request.user.perfil.regionais.all().order_by('nome')

    context = {
        'inventarios': inventarios,
        'regionais': regionais,
        'perfil': request.user.perfil,
        'filtros': {
            'sigla': sigla,
            'loja': loja,
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'regional_id': regional_id,
        }
    }
    return render(request, 'insumos/lista_inventarios.html', context)

@login_required
def editar_inventario(request, pk):
    inventario = get_object_or_404(Inventario, pk=pk)
    if not request.user.perfil.is_admin and not request.user.perfil.is_gestor:
        messages.error(request, 'Você não tem permissão para editar.')
        return redirect('insumos:lista_inventarios')

    if request.method == 'POST':
        form = InventarioForm(request.POST, instance=inventario)
        if form.is_valid():
            # Atualiza campos principais
            inventario = form.save(commit=False)
            # Atualiza dados_brutos com os campos dinâmicos
            dados = {}
            for key, value in request.POST.items():
                if key.startswith('campo_'):
                    nome_campo = key.replace('campo_', '')
                    dados[nome_campo] = value
            inventario.dados_brutos = dados
            inventario.save()
            messages.success(request, 'Inventário atualizado com sucesso.')
            return redirect('insumos:lista_inventarios')
    else:
        form = InventarioForm(instance=inventario)

    return render(request, 'insumos/editar_inventario.html', {
        'form': form,
        'inventario': inventario
    })

@login_required
def editar_inventario_modal(request, inventario_id):
    if not request.user.perfil.is_admin:
        return JsonResponse({'error': 'Acesso negado'}, status=403)

    inventario = get_object_or_404(Inventario, pk=inventario_id)
    if request.method == 'POST':
        form = InventarioForm(request.POST, instance=inventario)
        if form.is_valid():
            form.save()
            return JsonResponse({'success': True})
        return JsonResponse({'errors': form.errors}, status=400)

    from django.template.loader import render_to_string
    form = InventarioForm(instance=inventario)
    html = render_to_string('insumos/partials/editar_inventario.html', {'form': form, 'inventario': inventario})
    return JsonResponse({'html': html})

@login_required
def exportar_excel(request):
    """Exporta todos os inventários para um arquivo Excel no mesmo formato do importado."""

    # Criar workbook
    wb = openpyxl.Workbook()

    # --- ABA 1: Siglas e Tipos ---
    ws_siglas = wb.active
    ws_siglas.title = "Siglas e Tipos"

    # Cabeçalho
    cabecalho_siglas = ['SIGLA', 'CLIENTE', 'SEGMENTO', 'STATUS', '', '2026', 'TOTAL CLIENTES', '', '', 'TIPO',
                        'DESCRIÇÃO']
    ws_siglas.append(cabecalho_siglas)

    # Dados dos clientes ativos
    clientes = Cliente.objects.filter(ativo=True).order_by('sigla')
    for cliente in clientes:
        ws_siglas.append([
            cliente.sigla,
            cliente.nome,
            '',  # SEGMENTO (se não tiver, deixar em branco)
            'ATIVO',
            '',
            '',
            '',
            '',
            '',
            '',
            ''
        ])

    # --- ABA 2: Alterações (opcional, pode deixar vazia ou com cabeçalho) ---
    ws_alteracoes = wb.create_sheet("Alterações")
    ws_alteracoes.append(['', 'REGISTRO DE ALTERAÇÕES - ' + datetime.now().strftime('%B %Y').upper()])
    ws_alteracoes.append(
        ['', 'Revisão', 'Data', 'Cliente', 'Nº da Loja', 'Descrição da Alteração', 'Regional', 'Solicitante', 'Obs.'])
    # Deixar vazio ou adicionar dados se tiver histórico de alterações

    # --- ABA 3: Dados do mês atual (ex: JUN) ---
    mes_atual = datetime.now().strftime('%b').upper()  # Ex: "JUN"
    aba_principal = mes_atual

    # Verificar se a aba já existe (se criamos "Siglas e Tipos" e "Alterações", a próxima é a 3ª)
    # Como já temos 2 abas, a próxima será a terceira
    ws_principal = wb.create_sheet(aba_principal)

    # Cabeçalho da planilha principal (mesmo do arquivo importado)
    cabecalho_principal = [
        '', 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
        21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35
    ]
    ws_principal.append(cabecalho_principal)

    # Segunda linha: cabeçalho das colunas (igual ao Excel)
    cabecalho_colunas = [
        '#', 'SIGLA', 'Nº DA LOJA', 'DATA', 'ENDEREÇO', 'BAIRRO/NOME DA LOJA', 'CIDADE', 'REGIONAL',
        'TIPO', 'PESSOAS', 'OBSERVAÇÃO', 'LÍDER', 'PONTO DE ENCONTRO', 'HORÁRIO DO PONTO DE ENCONTRO',
        'HORÁRIO DE INÍCIO', 'TIPO DA VISITA', 'RESPONSÁVEL PELA VISITA', 'DATA DA VISITA',
        'HORÁRIO DA VISITA', 'RELATÓRIO DE VISITA', 'PREP', 'HISTÓRICO EQUIPE', 'HISTÓRICO PEÇAS',
        'HISTÓRICO SATISFAÇÃO', 'HISTÓRICO PREPARAÇÃO', 'HISTÓRICO LÍDER', 'HISTÓRICO DATA',
        'EQUIPE PLAN', 'PREVISÃO DE PEÇAS', 'PROD MÉDIA', 'BID', 'CNPJ', 'CEP', 'ENVIO DA ESCALA', 'CHAVE'
    ]
    ws_principal.append(cabecalho_colunas)

    # Dados dos inventários (apenas os que estão planejados ou em andamento, ou todos?)
    inventarios = Inventario.objects.filter(
        status__in=['PLANEJADO', 'EM_ANDAMENTO']
    ).select_related('cliente', 'base')

    # Ordenar por data e cliente
    inventarios = inventarios.order_by('data_inicio', 'cliente__sigla')

    # Para cada inventário, criar uma linha no Excel
    for idx, inv in enumerate(inventarios, start=1):
        # Usar os dados do banco ou, se existir, os dados brutos salvos
        dados = inv.dados_brutos if inv.dados_brutos else {}

        linha = [
            idx,  # #
            inv.cliente.sigla,
            inv.loja,
            inv.data_inicio.strftime('%Y-%m-%d') if inv.data_inicio else '',
            inv.endereco or '',
            inv.bairro or '',
            inv.cidade or '',
            inv.base.nome,
            inv.tipo or dados.get('TIPO', ''),
            inv.pessoas or dados.get('PESSOAS', ''),
            inv.observacao or dados.get('OBSERVAÇÃO', ''),
            inv.lider or dados.get('LÍDER', ''),
            inv.ponto_encontro or dados.get('PONTO DE ENCONTRO', ''),
            inv.horario_ponto.strftime('%H:%M:%S') if inv.horario_ponto else dados.get('HORÁRIO DO PONTO DE ENCONTRO',
                                                                                       ''),
            inv.horario_inicio.strftime('%H:%M:%S') if inv.horario_inicio else dados.get('HORÁRIO DE INÍCIO', ''),
            inv.tipo_visita or dados.get('TIPO DA VISITA', ''),
            inv.responsavel_visita or dados.get('RESPONSÁVEL PELA VISITA', ''),
            inv.data_visita.strftime('%Y-%m-%d') if inv.data_visita else dados.get('DATA DA VISITA', ''),
            inv.horario_visita.strftime('%H:%M:%S') if inv.horario_visita else dados.get('HORÁRIO DA VISITA', ''),
            inv.relatorio_visita or dados.get('RELATÓRIO DE VISITA', ''),
            inv.prep or dados.get('PREP', ''),
            inv.historico_equipe or dados.get('HISTÓRICO EQUIPE', ''),
            inv.historico_pecas or dados.get('HISTÓRICO PEÇAS', ''),
            inv.historico_satisfacao or dados.get('HISTÓRICO SATISFAÇÃO', ''),
            inv.historico_preparacao or dados.get('HISTÓRICO PREPARAÇÃO', ''),
            inv.historico_lider or dados.get('HISTÓRICO LÍDER', ''),
            inv.historico_data.strftime('%Y-%m-%d') if inv.historico_data else dados.get('HISTÓRICO DATA', ''),
            inv.equipe_plan or dados.get('EQUIPE PLAN', ''),
            inv.previsao_pecas or dados.get('PREVISÃO DE PEÇAS', ''),
            inv.prod_media or dados.get('PROD MÉDIA', ''),
            inv.bid or dados.get('BID', ''),
            inv.cnpj or dados.get('CNPJ', ''),
            inv.cep or dados.get('CEP', ''),
            inv.envio_escala.strftime('%Y-%m-%d') if inv.envio_escala else dados.get('ENVIO DA ESCALA', ''),
            inv.chave or dados.get('CHAVE', ''),
        ]

        # Garantir que a linha tenha exatamente 35 colunas
        while len(linha) < 35:
            linha.append('')
        ws_principal.append(linha)

    # --- ABA 4: Aba OXX (se houver inventários OXX) ---
    inventarios_oxx = inventarios.filter(cliente__sigla='OXX')
    if inventarios_oxx.exists():
        aba_oxx = mes_atual + " OXX"
        ws_oxx = wb.create_sheet(aba_oxx)

        # Cabeçalho igual ao da aba principal
        ws_oxx.append(cabecalho_principal)
        ws_oxx.append(cabecalho_colunas)

        for idx, inv in enumerate(inventarios_oxx, start=1):
            dados = inv.dados_brutos if inv.dados_brutos else {}
            linha = [
                idx,
                inv.cliente.sigla,
                inv.loja,
                inv.data_inicio.strftime('%Y-%m-%d') if inv.data_inicio else '',
                inv.endereco or '',
                inv.bairro or '',
                inv.cidade or '',
                inv.base.nome,
                inv.tipo or dados.get('TIPO', ''),
                inv.pessoas or dados.get('PESSOAS', ''),
                inv.observacao or dados.get('OBSERVAÇÃO', ''),
                inv.lider or dados.get('LÍDER', ''),
                inv.ponto_encontro or dados.get('PONTO DE ENCONTRO', ''),
                inv.horario_ponto.strftime('%H:%M:%S') if inv.horario_ponto else dados.get(
                    'HORÁRIO DO PONTO DE ENCONTRO', ''),
                inv.horario_inicio.strftime('%H:%M:%S') if inv.horario_inicio else dados.get('HORÁRIO DE INÍCIO', ''),
                inv.tipo_visita or dados.get('TIPO DA VISITA', ''),
                inv.responsavel_visita or dados.get('RESPONSÁVEL PELA VISITA', ''),
                inv.data_visita.strftime('%Y-%m-%d') if inv.data_visita else dados.get('DATA DA VISITA', ''),
                inv.horario_visita.strftime('%H:%M:%S') if inv.horario_visita else dados.get('HORÁRIO DA VISITA', ''),
                inv.relatorio_visita or dados.get('RELATÓRIO DE VISITA', ''),
                inv.prep or dados.get('PREP', ''),
                inv.historico_equipe or dados.get('HISTÓRICO EQUIPE', ''),
                inv.historico_pecas or dados.get('HISTÓRICO PEÇAS', ''),
                inv.historico_satisfacao or dados.get('HISTÓRICO SATISFAÇÃO', ''),
                inv.historico_preparacao or dados.get('HISTÓRICO PREPARAÇÃO', ''),
                inv.historico_lider or dados.get('HISTÓRICO LÍDER', ''),
                inv.historico_data.strftime('%Y-%m-%d') if inv.historico_data else dados.get('HISTÓRICO DATA', ''),
                inv.equipe_plan or dados.get('EQUIPE PLAN', ''),
                inv.previsao_pecas or dados.get('PREVISÃO DE PEÇAS', ''),
                inv.prod_media or dados.get('PROD MÉDIA', ''),
                inv.bid or dados.get('BID', ''),
                inv.cnpj or dados.get('CNPJ', ''),
                inv.cep or dados.get('CEP', ''),
                inv.envio_escala.strftime('%Y-%m-%d') if inv.envio_escala else dados.get('ENVIO DA ESCALA', ''),
                inv.chave or dados.get('CHAVE', ''),
            ]
            while len(linha) < 35:
                linha.append('')
            ws_oxx.append(linha)

    # --- Salvar arquivo ---
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    nome_arquivo = f'inventarios_{datetime.now().strftime("%Y_%m_%d")}.xlsx'
    response['Content-Disposition'] = f'attachment; filename="{nome_arquivo}"'

    wb.save(response)
    return response

def insumos_por_base(request):
    base_id = request.GET.get('base_id')
    if not base_id:
        return JsonResponse({'insumos': []})

    # Buscar todos os insumos ativos
    insumos = Insumo.objects.filter(ativo=True).select_related('categoria')
    data = []
    for insumo in insumos:
        saldo = MovimentacaoService.saldo(base_id, insumo)
        if saldo > 0:
            data.append({
                'id': insumo.id,
                'descricao': insumo.descricao,
                'categoria': insumo.categoria.nome,
                'unidade': insumo.unidade_medida,
                'saldo': float(saldo),
            })
    return JsonResponse({'insumos': data})

@login_required
def lista_checklists(request):
    if request.user.perfil.is_admin:
        checklists = ChecklistDiario.objects.all().select_related('inventario__cliente', 'inventario__base')
    else:
        checklists = ChecklistDiario.objects.filter(
            inventario__base__in=request.user.perfil.regionais.all()
        ).select_related('inventario__cliente', 'inventario__base')

    checklists = checklists.order_by('-data_inicio')

    context = {
        'checklists': checklists,
        'perfil': request.user.perfil,
    }
    return render(request, 'insumos/lista_checklists.html', context)

@login_required
def finalizar_checklist(request, pk):
    checklist = get_object_or_404(ChecklistDiario.objects.select_related('inventario__base', 'inventario__cliente'), pk=pk)

    # Verifica permissão (admin, gestor, ou responsável)
    if not request.user.perfil.is_admin:
        if not request.user.perfil.is_gestor and checklist.responsavel != request.user:
            messages.error(request, 'Você não tem permissão para finalizar este checklist.')
            return redirect('insumos:lista_checklists')

    # Verifica se já está finalizado
    if checklist.status == 'FINALIZADO':
        messages.warning(request, 'Este checklist já foi finalizado.')
        return redirect('insumos:lista_checklists')

    try:
        with transaction.atomic():
            ChecklistService.finalizar(checklist=checklist, usuario=request.user)
        messages.success(request, f'Checklist #{checklist.id} finalizado com sucesso!')
    except ValueError as e:
        messages.error(request, f'Erro ao finalizar checklist: {str(e)}')
    except Exception as e:
        messages.error(request, f'Erro inesperado: {str(e)}')

    return redirect('insumos:lista_checklists')

@login_required
def checklist_detail(request, pk):
    checklist = get_object_or_404(ChecklistDiario.objects.select_related(
        'inventario__cliente', 'inventario__base'
    ), pk=pk)

    # Verifica permissão
    if not request.user.perfil.is_admin:
        if checklist.inventario.base_id not in request.user.perfil.regionais_ids:
            messages.error(request, 'Você não tem acesso a este checklist.')
            return redirect('insumos:lista_checklists')

    if request.method == 'POST':
        if checklist.status == 'FINALIZADO':
            messages.warning(request, 'Este checklist já foi finalizado.')
            return redirect('insumos:checklist_detail', pk=checklist.pk)

        try:
            with transaction.atomic():
                for item in checklist.itens.select_related('insumo'):
                    ChecklistService.atualizar_item(
                        item=item,
                        utilizada=request.POST.get(f'utilizada_{item.id}', 0),
                        retornada=request.POST.get(f'retornada_{item.id}', 0),
                        perdida=request.POST.get(f'perdida_{item.id}', 0),
                    )

                for item_equip in checklist.equipamentos_utilizados.select_related('equipamento'):
                    retorno_confirmado = request.POST.get(f'equip_retorno_{item_equip.id}')
                    if retorno_confirmado and not item_equip.data_retorno:
                        item_equip.data_retorno = timezone.now()
                        item_equip.save(update_fields=['data_retorno'])

                if request.POST.get('acao') == 'finalizar':
                    ChecklistService.atualizar_tags_finalizacao(
                        checklist=checklist,
                        data=request.POST,
                    )
                    ChecklistService.finalizar(checklist=checklist, usuario=request.user)
                    messages.success(request, f'Checklist #{checklist.id} finalizado com sucesso!')
                    return redirect('insumos:lista_checklists')

                for item_lote in checklist.lotes_tags_movimentados.select_related('lote'):
                    valor = request.POST.get(f'tag_final_item_{item_lote.id}', '').strip()
                    if valor:
                        ChecklistService.atualizar_retorno_lote_tag(
                            item_lote=item_lote,
                            numero_final_utilizado=valor,
                        )

            messages.success(request, 'Retorno do checklist salvo com sucesso.')

        except ValueError as e:
            messages.error(request, f'Erro no retorno do checklist: {str(e)}')
        except Exception as e:
            messages.error(request, f'Erro inesperado: {str(e)}')

        return redirect('insumos:checklist_detail', pk=checklist.pk)

    tags = checklist.lotes_tags_movimentados.select_related('lote', 'rolo')

    context = {
        'checklist': checklist,
        'itens': checklist.itens.select_related('insumo'),
        'equipamentos': checklist.equipamentos_utilizados.select_related('equipamento__produto'),
        'tags': tags,
        'total_tags_utilizadas': sum(tag.quantidade_utilizada for tag in tags),
    }
    return render(request, 'insumos/checklist_detail.html', context)

@login_required
def editar_itens_checklist(request, pk):
    checklist = get_object_or_404(ChecklistDiario.objects.select_related('inventario__base'), pk=pk)

    # Verifica permissão
    if not request.user.perfil.is_admin and checklist.inventario.base_id not in request.user.perfil.regionais_ids:
        messages.error(request, 'Você não tem acesso a este checklist.')
        return redirect('insumos:lista_checklists')

    if checklist.status == 'FINALIZADO':
        messages.warning(request, 'Este checklist já está finalizado.')
        return redirect('insumos:lista_checklists')

    if request.method == 'POST':
        for item in checklist.itens.select_related('insumo'):
            utilizada = request.POST.get(f'utilizada_{item.id}', 0)
            retornada = request.POST.get(f'retornada_{item.id}', 0)
            perdida = request.POST.get(f'perdida_{item.id}', 0)

            try:
                ChecklistService.atualizar_item(
                    item=item,
                    utilizada=utilizada,
                    retornada=retornada,
                    perdida=perdida
                )
            except ValueError as e:
                messages.error(request, f'Erro no item "{item.insumo.descricao}": {str(e)}')
                return redirect('insumos:editar_itens_checklist', pk=checklist.id)

        messages.success(request, 'Itens do checklist atualizados com sucesso!')
        return redirect('insumos:checklist_detail', pk=checklist.id)

    context = {
        'checklist': checklist,
        'itens': checklist.itens.select_related('insumo'),
    }
    return render(request, 'insumos/editar_itens_checklist.html', context)

@login_required
def ultimo_checklist_por_loja(request):
    cliente_sigla = request.GET.get('cliente')
    loja = request.GET.get('loja')
    base_id = request.GET.get('base')

    if not cliente_sigla or not loja or not base_id:
        return JsonResponse({'error': 'Parâmetros incompletos'}, status=400)

    # Busca o último checklist daquela loja (finalizado ou em execução)
    ultimo = ChecklistDiario.objects.filter(
        inventario__cliente__sigla=cliente_sigla,
        inventario__loja=loja,
        inventario__base_id=base_id,
        status__in=['FINALIZADO', 'EM_EXECUCAO']
    ).order_by('-data_inicio').first()

    if not ultimo:
        return JsonResponse({'dados': None})

    # Monta resposta
    data = {
        'checklist_id': ultimo.id,
        'data': ultimo.data_inicio.strftime('%d/%m/%Y %H:%M'),
        'insumos': [],
        'equipamentos': [],
        'tags': []
    }

    # Insumos
    for item in ultimo.itens.select_related('insumo'):
        data['insumos'].append({
            'insumo_id': item.insumo.id,
            'enviada': float(item.quantidade_enviada),
            'utilizada': float(item.quantidade_utilizada or 0),
            'retornada': float(item.quantidade_retornada or 0),
            'perdida': float(item.quantidade_perdida or 0),
        })

    # Equipamentos
    for eq in ultimo.equipamentos_utilizados.select_related('equipamento'):
        data['equipamentos'].append({
            'id': eq.equipamento.id,
            'categoria': eq.equipamento.produto.categoria.lower(),  # coletor, router, etc.
            'tag_saida': eq.tag_saida,
            'tag_volta': eq.tag_volta,
        })

    # Tags (LoteTag) - se houver
    for tag in ultimo.lotes_tags_movimentados.select_related('lote', 'rolo'):
        data['tags'].append({
            'lote_id': tag.lote.id,
            'rolo_id': tag.rolo_id,
            'inicial_utilizado': tag.numero_inicial_utilizado,
            'final_utilizado': tag.numero_final_utilizado,
        })

    return JsonResponse({'dados': data})

@login_required
def editar_checklist(request, pk):
    checklist = get_object_or_404(ChecklistDiario.objects.select_related(
        'inventario__base', 'inventario__cliente'
    ), pk=pk)

    # Verifica permissão (admin, gestor, ou responsável)
    if not request.user.perfil.is_admin:
        if not request.user.perfil.is_gestor and checklist.responsavel != request.user:
            messages.error(request, 'Você não tem permissão para editar este checklist.')
            return redirect('insumos:lista_checklists')

    if checklist.status == 'FINALIZADO':
        messages.warning(request, 'Checklist já finalizado, não pode ser editado.')
        return redirect('insumos:checklist_detail', pk=checklist.pk)

    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Atualizar insumos (quantidades utilizada, retornada, perdida)
                for item in checklist.itens.select_related('insumo'):
                    utilizada = request.POST.get(f'insumo_{item.insumo.id}_utilizada', 0)
                    retornada = request.POST.get(f'insumo_{item.insumo.id}_retornada', 0)
                    perdida = request.POST.get(f'insumo_{item.insumo.id}_perdida', 0)
                    # Atualiza o item
                    item.quantidade_utilizada = Decimal(utilizada or 0)
                    item.quantidade_retornada = Decimal(retornada or 0)
                    item.quantidade_perdida = Decimal(perdida or 0)
                    item.save(update_fields=['quantidade_utilizada', 'quantidade_retornada', 'quantidade_perdida'])

                # Atualizar equipamentos (tag_volta = retorno confirmado)
                for eq in checklist.equipamentos_utilizados.all():
                    # Identifica a categoria para buscar o campo de retorno
                    categoria = eq.equipamento.produto.categoria.lower()
                    retorno = request.POST.get(f'retorno_equip_{categoria}', '')
                    if retorno:
                        eq.tag_volta = retorno
                        eq.save(update_fields=['tag_volta'])

                messages.success(request, 'Checklist atualizado com sucesso!')
                return redirect('insumos:checklist_detail', pk=checklist.pk)

        except Exception as e:
            messages.error(request, f'Erro ao atualizar: {str(e)}')

    # GET: carrega o formulário de edição
    # Precisamos dos mesmos dados do checklist para popular o template
    # Vamos usar o mesmo template 'estoque/checklist.html', mas com dados preenchidos

    # Prepara listas de equipamentos (como na view de criação)
    from estoque.models import Equipamento
    from insumos.models import Insumo

    regionais_ids = request.user.perfil.regionais_ids
    if request.user.perfil.is_admin:
        equipamentos = Equipamento.objects.filter(status='ATIVO')
        lotes_tags = RoloTag.objects.filter(status='DISPONIVEL', lote__ativo=True).select_related('lote', 'lote__base')
    else:
        equipamentos = Equipamento.objects.filter(status='ATIVO', regional_id__in=regionais_ids)
        lotes_tags = RoloTag.objects.filter(
            status='DISPONIVEL',
            lote__ativo=True,
            lote__base_id__in=regionais_ids,
        ).select_related('lote', 'lote__base')

    # Obtém itens do checklist para pré-preencher
    itens_checklist = []  # Não precisamos da lista fixa aqui, pois vamos preencher com os dados do checklist

    # Insumos já existentes no checklist
    insumos_do_checklist = checklist.itens.select_related('insumo')

    context = {
        'checklist': checklist,
        'coletores': equipamentos.filter(produto__categoria='Coletores'),
        'impressoras': equipamentos.filter(produto__categoria='Impressoras'),
        'notebooks': equipamentos.filter(produto__categoria='Notebooks'),
        'routers': equipamentos.filter(produto__categoria='Routers'),
        'inventarios': [checklist.inventario],  # apenas o inventário atual
        'insumos': insumos_do_checklist,  # insumos já adicionados
        'lotes_tags': lotes_tags,
        'lotes_tags_selecionados': checklist.lotes_tags_movimentados.select_related('lote'),
        'url_name': 'editar_checklist',
        'editando': True,  # flag para indicar que é edição
        'equipamentos_selecionados': checklist.equipamentos_utilizados.all(),
    }
    return render(request, 'estoque/checklist.html', context)
