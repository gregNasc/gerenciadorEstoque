from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils import timezone
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors
from openpyxl import Workbook
from .services.emprestimo_service import EmprestimoService
from insumos.models import Inventario, Insumo
from insumos.services.checklist_service import ChecklistService
from django.db import transaction
from .forms import EquipamentoForm
from django.http import HttpResponse
from .models import (Produto, Equipamento, Transferencia, Sick, Historico, Base, Perfil, Empresa, Solicitacao, SolicitacaoItem, AlocacaoSolicitacaoItem, TransferenciaItem, StatusEquipamento) #Regional
from .models import (Comunicado, ComunicadoArquivo, ComunicadoLeitura, ComunicadoOculto, Mensagem, MensagemDestino, MensagemArquivo, Empresa, Notificacao, Emprestimo, ItemEmprestimo, GrupoRegional)
from .models import (PendenciaTransferencia, DivergenciaTransferencia)
from estoque.models import Base
from .utils import notificar_pendencia_transferencia
from .utils import filtrar_por_empresa, qs_equipamentos, qs_historico, qs_bases
from django.db.models import Count, Q, F
from django.utils.dateparse import parse_date
from estoque.models import Equipamento
from insumos.models import ChecklistDiario
from insumos.models import LoteTag, RoloTag
from django.utils import timezone
from datetime import datetime, time
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from openpyxl import Workbook
from collections import OrderedDict
from django.contrib.auth.decorators import login_required
from .decorators import role_required
from datetime import date
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .utils import EstoqueService
from .security import secure_queryset
from estoque.permissions import (pode_gerenciar_sick, pode_enviar_comunicados,)
from estoque.permissions import pode_realizar_manutencao_sick
#from estoque.services.transferencia_services import gerar_transferencias_da_solicitacao
import json
from django.urls import reverse
import re
from uuid import uuid4
from collections import defaultdict
from .services.estoque_service import get_estoque_por_produto
from django.contrib.auth import authenticate


# ----------------- DASHBOARD -----------------
@login_required
#@cache_page(60 * 5)
def index(request):
    perfil = request.user.perfil
    equipamentos = secure_queryset(
        Equipamento.objects.select_related('regional', 'produto'),
        request.user
    )

    # Filtros
    categoria = request.GET.get('categoria')
    produto_id = request.GET.get('produto')
    regional_id = request.GET.get('regional')
    inventory_id = request.GET.get('inventory')

    if inventory_id and inventory_id.isdigit():
        equipamentos = equipamentos.filter(
            regional__empresa_id=inventory_id
        )

    if categoria:
        equipamentos = equipamentos.filter(produto__categoria=categoria)

    if produto_id and produto_id.isdigit():
        equipamentos = equipamentos.filter(produto_id=produto_id)

    regional_id = request.GET.get('regional')
    if regional_id and regional_id.isdigit():
        if not perfil.is_admin and not perfil.regionais.filter(id=regional_id).exists():
            messages.error(request, "Acesso negado a esta regional.")
            return redirect('estoque:index')
        equipamentos = equipamentos.filter(regional_id=regional_id)

    # KPI SUPERIOR

    if categoria:
        # Por produto
        produtos_na_categoria = list(
            equipamentos
            .values(
                'produto__id',
                'produto__descricao',
            )
            .annotate(
                total=Count('id'),
                ativos=Count('id', filter=Q(status='ATIVO')),
                sick=Count('id', filter=Q(status='SICK')),
                inativos=Count('id', filter=Q(status='INATIVO')),
                transferencia=Count('id', filter=Q(status='TRANSFERENCIA')),
                emprestados=Count('id', filter=Q(status='EMPRESTADO')),
                manutencao=Count('id', filter=Q(status='MANUTENCAO')),
            )
            .order_by('produto__descricao')
        )

        for p in produtos_na_categoria:
            p['id'] = p.pop('produto__id')
            p['nome'] = p.pop('produto__descricao')

    else:
        # Por categoria
        produtos_na_categoria = list(
            equipamentos
            .values('produto__categoria')
            .annotate(
                total=Count('id'),
                ativos=Count('id', filter=Q(status='ATIVO')),
                sick=Count('id', filter=Q(status='SICK')),
                inativos=Count('id', filter=Q(status='INATIVO')),
                transferencia=Count('id', filter=Q(status='TRANSFERENCIA')),
                emprestados=Count('id', filter=Q(status='EMPRESTADO')),
                manutencao=Count('id', filter=Q(status='MANUTENCAO')),
            )
            .order_by('produto__categoria')
        )

        for c in produtos_na_categoria:
            c['id'] = c['produto__categoria']
            c['nome'] = c['produto__categoria']
            c['icone'] = 'bi-box'


    # KPIs REGIONAIS
    regionais_ids = equipamentos.values_list('regional_id', flat=True).distinct()
    regionais_lista = Base.objects.filter(id__in=regionais_ids).order_by('nome')

    kpis_regionais = []

    for regional in regionais_lista:
        equip_regional = equipamentos.filter(regional=regional)

        total = equip_regional.count()
        ativos = equip_regional.filter(status='ATIVO').count()
        sick = equip_regional.filter(status='SICK').count()
        inativos = equip_regional.filter(status='INATIVO').count()

        regional_data = {
            'regional__id': regional.id,
            'regional__nome': regional.nome,
            'total': total,
            'ativos': ativos,
            'sick': sick,
            'inativos': inativos,
            'disponibilidade': round((ativos / total * 100), 2) if total else 0,
        }

        if categoria:
            # detalhado por produto
            produtos = equip_regional.values(
                'produto__id', 'produto__descricao'
            ).annotate(
                total=Count('id'),
                ativos=Count('id', filter=Q(status='ATIVO')),
                sick=Count('id', filter=Q(status='SICK')),
                transferencia=Count('id', filter=Q(status='TRANSFERENCIA')),
            ).order_by('produto__descricao')

            regional_data['produtos_detalhados'] = list(produtos)

        else:
            # resumo por categoria
            categorias_base = ['Coletores', 'Impressoras', 'Notebooks', 'Routers']

            produtos_query = (
                equip_regional
                .values('produto__categoria')
                .annotate(
                    total=Count('id'),
                    ativos=Count('id', filter=Q(status='ATIVO')),
                    sick=Count('id', filter=Q(status='SICK')),
                    inativos=Count('id', filter=Q(status='INATIVO')),
                    transferencia=Count('id', filter=Q(status='TRANSFERENCIA')),
                )
            )

            produtos_dict = {p['produto__categoria']: p for p in produtos_query}

            regional_data['produtos'] = {
                categoria: {
                    'total': produtos_dict.get(categoria, {}).get('total', 0),
                    'ativos': produtos_dict.get(categoria, {}).get('ativos', 0),
                    'sick': produtos_dict.get(categoria, {}).get('sick', 0),
                    'transferencia': produtos_dict.get(categoria, {}).get('transferencia', 0),
                }
                for categoria in categorias_base
            }
        kpis_regionais.append(regional_data)


    # SELECTS
    produtos_lista = Produto.objects.all()
    if categoria:
        produtos_lista = produtos_lista.filter(categoria=categoria)

    regionais_select = Base.objects.all()

    if inventory_id and inventory_id.isdigit():
        regionais_select = regionais_select.filter(
            empresa_id=inventory_id
        )

    regionais_select = regionais_select.order_by('nome')
    empresas = Empresa.objects.all().order_by('nome')

    context = {
        'produtos_na_categoria': produtos_na_categoria,
        'categoria_selecionada': categoria,
        'kpis_regionais': kpis_regionais,
        'produtos_lista': produtos_lista,
        'regionais': regionais_select,
        'filtro_produto_id': produto_id,
        'filtro_regional_id': regional_id,
        'empresas': empresas,
        'filtro_inventory_id': inventory_id,
    }

    return render(request, 'estoque/index.html', context)

@login_required
def api_kpis_json(request):
    equipamentos = secure_queryset(
        Equipamento.objects.select_related('regional', 'produto'),
        request.user
    )

    produto_id = request.GET.get('produto')
    regional_id = request.GET.get('regional')

    if produto_id and produto_id.isdigit():
        equipamentos = equipamentos.filter(produto_id=produto_id)
    if regional_id and regional_id.isdigit():
        equipamentos = equipamentos.filter(regional_id=regional_id)

    kpis = EstoqueService.get_kpis_gerais(equipamentos)
    disponibilidade = EstoqueService.get_disponibilidade(equipamentos)

    regionais_lista = Base.objects.all().order_by('nome')
    kpis_regionais = EstoqueService.get_kpis_por_regional(equipamentos, regionais_lista)

    return JsonResponse({
        'kpis': kpis,
        'disponibilidade': disponibilidade,
        'kpis_regionais': kpis_regionais,
    })

@login_required
@role_required('admin', 'gestor')
def detalhes_regional_api(request, regional_id):
    perfil = request.user.perfil

    if not perfil.is_admin:
        if not perfil.regionais.filter(id=regional_id).exists():
            return JsonResponse({'erro': 'Acesso negado.'}, status=403)

    equipamentos = secure_queryset(
        Equipamento.objects.select_related('regional', 'produto'),
        request.user
    ).filter(regional_id=regional_id)

    regional = Base.objects.filter(id=regional_id).only('id', 'nome').first()
    if not regional:
        return JsonResponse({'erro': 'Regional não encontrada'}, status=404)

    produtos_agrupados = (
        equipamentos
        .values(
            'produto__id',
            'produto__descricao',
            'produto__categoria'
        )
        .annotate(
            total=Count('id'),
            ativos=Count('id', filter=Q(status='ATIVO')),
            sick=Count('id', filter=Q(status='SICK')),
            inativos=Count('id', filter=Q(status='INATIVO')),
            manutencao=Count('id', filter=Q(status='MANUTENCAO')),
        )
        .order_by('produto__categoria', 'produto__descricao')
    )

    categorias_dict = defaultdict(list)

    for p in produtos_agrupados:
        categorias_dict[p['produto__categoria']].append({
            'id': p['produto__id'],
            'nome': p['produto__descricao'],
            'total': p['total'],
            'ativos': p['ativos'],
            'sick': p['sick'],
            'inativos': p['inativos'],
            'manutencao': p['manutencao'],
            'transferencia': 0,
        })

    produtos_detalhados = [
        {
            'categoria': cat,
            'produtos': produtos
        }
        for cat, produtos in categorias_dict.items()
    ]

    total = equipamentos.count()
    ativos = equipamentos.filter(status='ATIVO').count()

    disponibilidade = round((ativos / total * 100), 2) if total else 0

    return JsonResponse({
        'categorias': produtos_detalhados,
        'regional_id': regional.id,
        'regional_nome': regional.nome,
        'total_regional': total,
        'disponibilidade_regional': disponibilidade,
    })

@login_required
@role_required('admin', 'gestor')
def api_regionais_produto(request, produto_id):
    qs = secure_queryset(
        Equipamento.objects.filter(produto_id=produto_id),
        request.user
    )
    dados = (
        qs
        .values('regional__id', 'regional__nome')
        .annotate(total=Count('id'))
        .order_by('regional__nome')
    )
    return JsonResponse({'regionais': list(dados)})

@login_required
@role_required('admin', 'gestor')
def lista_regionais_json(request):
    from django.apps import apps
    Base = apps.get_model('estoque', 'Base')
    perfil = request.user.perfil
    if perfil.is_admin():
        regionais = Base.objects.all()
    else:
        regionais = perfil.regionais.all()
    data = [{'id': r.id, 'nome': r.nome} for r in regionais]
    return JsonResponse(data, safe=False)

@receiver(post_save, sender=User)
def criar_perfil(sender, instance, created, **kwargs):
    if created:
        Perfil.objects.get_or_create(user=instance)

@login_required
@role_required('admin')
def cadastrar_usuario(request):
    from django.contrib.auth.models import User
    from .models import Perfil, Empresa, Base
    from django.db import transaction

    if request.method == 'POST':
        try:
            with transaction.atomic():
                username = request.POST.get('username', '').strip()
                password = request.POST.get('password', '')
                first_name = request.POST.get('first_name', '').strip()
                email = request.POST.get('email', '').strip()
                role = request.POST.get('role', 'operador')
                regionais_ids = request.POST.getlist('regionais')

                # ---------------- VALIDAÇÕES ----------------
                if not username:
                    messages.error(request, "Informe o nome de usuário.")
                    return redirect('estoque:cadastrar_usuario')

                if not password:
                    messages.error(request, "Informe a senha.")
                    return redirect('estoque:cadastrar_usuario')

                if len(password) < 6:
                    messages.error(request, "Senha mínima de 6 caracteres.")
                    return redirect('estoque:cadastrar_usuario')

                if User.objects.filter(username=username).exists():
                    messages.error(request, f"Usuário '{username}' já existe.")
                    return redirect('estoque:cadastrar_usuario')

                if email and User.objects.filter(email=email).exists():
                    messages.error(request, f"E-mail '{email}' já está em uso.")
                    return redirect('estoque:cadastrar_usuario')

                # ---------------- REGRA REGIONAL ----------------
                empresa = None
                regionais = Base.objects.none()

                if role != 'admin':
                    if not regionais_ids:
                        messages.error(request, "Selecione ao menos uma regional.")
                        return redirect('estoque:cadastrar_usuario')

                    regionais = Base.objects.filter(id__in=regionais_ids).select_related('empresa')

                    if not regionais.exists():
                        messages.error(request, "Regionais inválidas.")
                        return redirect('estoque:cadastrar_usuario')

                    empresa = regionais.first().empresa

                # ---------------- CRIA USUÁRIO ----------------
                user = User.objects.create_user(
                    username=username,
                    password=password,
                    first_name=first_name,
                    email=email,
                    is_active=True
                )

                # ---------------- PERFIL ----------------
                perfil, _ = Perfil.objects.get_or_create(user=user)

                perfil.role = role
                perfil.empresa = empresa if role != 'admin' else None
                perfil.save()

                if role != 'admin':
                    perfil.regionais.set(regionais)
                else:
                    perfil.regionais.clear()

                messages.success(request, f"Usuário '{username}' criado com sucesso!")
                return redirect('estoque:cadastrar_usuario')

        except Exception as e:
            messages.error(request, f"Erro ao criar usuário: {str(e)}")
            return redirect('estoque:cadastrar_usuario')

    context = {
        'empresas': Empresa.objects.all().order_by('nome'),
        'regionais': Base.objects.select_related('empresa').all().order_by('empresa__nome', 'nome'),
        'roles': Perfil.Role.choices,
    }

    return render(request, 'estoque/cadastrar_usuarios.html', context)

def filtrar_por_perfil(queryset, user):
    perfil = user.perfil

    if perfil.is_admin():
        return queryset

    return queryset.filter(regional__in=perfil.regionais_ids)

def login_view(request):
    if request.user.is_authenticated:
        return redirect('estoque:index')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            Perfil.objects.get_or_create(
                user=user,
                defaults={'role': 'operador'}
            )
            messages.success(request, 'Bem-vindo de volta!')
            return redirect('estoque:index')
        else:
            messages.error(request, 'Usuário ou senha inválidos.')
            return render(request, 'registration/login.html')

    return render(request, 'registration/login.html')

def logout_view(request):
    logout(request)
    messages.success(request, 'Você saiu do sistema com sucesso!')
    return redirect('estoque:login')

@login_required
def verificar_consistencia_api(request):
    equipamentos = secure_queryset(
        Equipamento.objects.select_related('regional', 'produto'),
        request.user
    )

    kpis_geral = EstoqueService.get_kpis_gerais(equipamentos)

    regionais = Base.objects.all()
    soma_regionais = {
        'total': 0,
        'ativos': 0,
        'sick': 0,
    }

    for regional in regionais:
        equip_regional = equipamentos.filter(regional=regional)
        kpis_regional = EstoqueService.get_kpis_gerais(equip_regional)
        soma_regionais['total'] += kpis_regional['total']
        soma_regionais['ativos'] += kpis_regional['ativos']
        soma_regionais['sick'] += kpis_regional['sick']

    consistente = (
            kpis_geral['total'] == soma_regionais['total'] and
            kpis_geral['ativos'] == soma_regionais['ativos'] and
            kpis_geral['sick'] == soma_regionais['sick']
    )

    return JsonResponse({
        'consistente': consistente,
        'geral': kpis_geral,
        'soma_regionais': soma_regionais,
        'diferencas': {
            'total': kpis_geral['total'] - soma_regionais['total'],
            'ativos': kpis_geral['ativos'] - soma_regionais['ativos'],
            'sick': kpis_geral['sick'] - soma_regionais['sick'],
        }
    })

# ----------------- CADASTRAR PRODUTO -----------------
@login_required
@role_required('admin', 'gestor', 'operador')
def cadastrar_equipamento_view(request):
    if request.method == 'POST':
        form = EquipamentoForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            equipamento = form.save()
            print("FOTO:", equipamento.foto)
            print("URL:", equipamento.foto.url if equipamento.foto else "SEM FOTO")
            Historico.objects.create(
                equipamento=equipamento,
                tipo_acao='CRIACAO',
                usuario=request.user,
                detalhes={'mensagem': 'Equipamento cadastrado'}
            )

            messages.success(request, "Equipamento cadastrado com sucesso.")
            return redirect('estoque:index')
    else:
        form = EquipamentoForm(user=request.user)

    return render(request, 'estoque/cadastrar_equipamento.html', {
        'form': form
    })

@login_required
def produtos_por_categoria(request):
    categoria = request.GET.get('categoria')

    produtos = Produto.objects.filter(
        categoria=categoria
    ).order_by('descricao').values('id', 'descricao')

    return JsonResponse({
        'produtos': list(produtos)
    })

# ----------------- ESTOQUE -----------------
@login_required
@role_required('admin', 'gestor')
def estoque_view(request):

    perfil = request.user.perfil

    equipamentos = secure_queryset(
        Equipamento.objects.select_related(
            'regional',
            'produto'
        ),
        request.user
    )

    regional_id = request.GET.get('regional')

    if regional_id and regional_id.isdigit():

        equipamentos = equipamentos.filter(
            regional_id=regional_id
        )

    status_em_transito = [
        'PENDENTE',
        'ENVIADO',
        'EM_TRANSITO',
        'AGUARDANDO_RECEBIMENTO',
        'TRANSFERENCIA'
    ]

    produtos_agrupados = (
        equipamentos
        .values('produto__id', 'produto__descricao')
        .annotate(
            total=Count('id'),

            ativos=Count(
                'id',
                filter=Q(status='ATIVO')
            ),

            sick=Count(
                'id',
                filter=Q(status='SICK')
            ),

            manutencao=Count(
                'id',
                filter=Q(status='MANUTENCAO')
            ),

            em_transito=Count(
                'id',
                filter=Q(status__in=status_em_transito)
            ),

            inativos=Count(
                'id',
                filter=Q(status='INATIVO')
            ),
        )
        .order_by('produto__descricao')
    )

    produtos_processados = []

    for item in produtos_agrupados:

        inativos = item['inativos']

        disponibilidade = 0

        if item['total'] > 0:

            disponibilidade = int(
                (item['ativos'] / item['total']) * 100
            )

        produtos_processados.append({
            **item,
            'inativos': inativos,
            'disponibilidade': disponibilidade,
        })

    if perfil.is_admin:

        regionais = (
            Base.objects
            .all()
            .order_by('nome')
        )

    else:

        regionais = (
            perfil.regionais
            .all()
            .order_by('nome')
        )

    return render(
        request,
        'estoque/estoque.html',
        {
            'produtos_agrupados': produtos_processados,
            'regionais': regionais,
            'regional_selecionada': regional_id
        }
    )


# ----------------- DETALHES DO PRODUTO -----------------
@login_required
@role_required('admin', 'gestor')
def detalhes_produto_view(request, produto_id, regional_id):

    perfil = request.user.perfil

    regional = get_object_or_404(Base, id=regional_id)
    produto = get_object_or_404(Produto, id=produto_id)

    base_qs = secure_queryset(
        Equipamento.objects.select_related('regional', 'produto'),
        request.user
    )

    equipamentos = base_qs.filter(
        produto_id=produto_id,
        regional=regional
    )

    if request.method == 'POST':
        acao = request.POST.get('acao')

        # ---------------- SICK ----------------
        if acao == 'sick':

            if not perfil.pode_marcar_sick():
                messages.error(request, "Sem permissão.")
                return redirect(request.path)

            equipamento = get_object_or_404(Equipamento, id=equipamento_id)

            equipamento.status = 'SICK'
            equipamento.save()

            Sick.objects.create(
                equipamento=equipamento,
                motivo=request.POST.get('motivo_sick'),
                categoria="OPERACIONAL"
            )

            messages.success(request, "Equipamento movido para SICK.")
            return redirect(request.path)

        # ---------------- TRANSFERÊNCIA ----------------
        elif acao == 'transferir':

            if not perfil.pode_transferir():
                messages.error(request, "Sem permissão.")
                return redirect(request.path)

            ids = request.POST.getlist('equipamentos_selecionados')

            if not ids:
                messages.error(request, "Selecione ao menos um equipamento.")
                return redirect(request.path)

            destino = get_object_or_404(Base, id=request.POST.get('regional_destino'))

            equipamentos = base_qs.filter(id__in=ids)

            sucesso = 0

            for equipamento in equipamentos:

                pode, motivo = pode_transferir(equipamento)

                if not pode:
                    messages.error(request, f"{equipamento.numero_serie} bloqueado: {motivo}")
                    continue

                iniciar_transferencia(equipamento, destino, request.user)
                sucesso += 1

            if sucesso:
                messages.success(request, f"{sucesso} transferência(s) criada(s).")

            return redirect(request.path)

@login_required
@role_required('admin', 'gestor')
def detalhes_produto(request, produto_id):

    perfil = request.user.perfil
    regional_id = request.GET.get('regional')

    qs = secure_queryset(
        Equipamento.objects.filter(produto_id=produto_id),
        request.user
    )

    dados_regionais = (
        qs
        .values(
            'regional__id',
            'regional__nome'
        )
        .annotate(
            total=Count('id')
        )
        .order_by('regional__nome')
    )

    if regional_id:
        qs = qs.filter(regional_id=regional_id)

    equipamentos = []

    for e in qs.select_related(
        'regional',
        'produto'
    ):

        pode, motivo = pode_transferir(e)

        equipamentos.append({
            "id": e.id,
            "numero_serie": e.numero_serie,
            "patrimonio": e.patrimonio,
            "status": e.status,
            "responsavel": e.responsavel,
            "foto": e.foto.url if e.foto else None,
            "pode_transferir": pode,
            "motivo_bloqueio": motivo,
            "regional": e.regional.nome if e.regional else None
        })

    transferencias = (
        Transferencia.objects
        .filter(
            itens__equipamento__produto_id=produto_id,
            status__in=['PENDENTE', 'EM_TRANSITO']
        )
        .select_related(
            'regional_origem',
            'regional_destino'
        )
        .distinct()
    )

    if perfil.role != 'admin':

        transferencias = transferencias.filter(
            regional_origem__in=perfil.regionais.all()
        )

    if regional_id:

        transferencias = transferencias.filter(
            regional_origem_id=regional_id
        )

    trans_list = []

    for t in transferencias:

        trans_list.append({
            "id": t.id,
            "origem": t.regional_origem.nome,
            "destino": t.regional_destino.nome,
            "status": t.status,
            "descricao": f"A caminho para {t.regional_destino.nome}"
        })

    return JsonResponse({
        "regionais": list(dados_regionais),
        "equipamentos": equipamentos,
        "transferencias": trans_list,
        "regional_id": regional_id
    })

# ----------------- SICK -----------------
@login_required
@role_required('admin', 'gestor')
def sick_view(request):

    perfil = request.user.perfil

    pode_acessar = (
            perfil.is_admin or
            perfil.is_gestor or
            pode_realizar_manutencao_sick(request.user)
    )

    if not pode_acessar:
        messages.error(request, "Sem permissão.")
        return redirect('estoque:index')

    if request.method == 'POST':

        sick_id = request.POST.get('sick_id')
        #acao = request.POST.get('acao')
        novo_status = request.POST.get('novo_status')

        motivo_manutencao = request.POST.get("motivo_manutencao")
        previsao_retorno = request.POST.get("previsao_retorno")

        if sick_id and novo_status:

            sick = get_object_or_404(
                Sick.objects.select_related('equipamento'),
                id=sick_id
            )

            # Permissão
            if not pode_realizar_manutencao_sick(request.user):
                messages.error(
                    request,
                    "Você não possui permissão para realizar manutenção SICK."
                )
                return redirect('estoque:sick')

            status_permitidos = [
                'ATIVO',
                'MANUTENCAO',
                'SUCATA',
                'INATIVO'
            ]

            if novo_status not in status_permitidos:
                messages.error(request, "Status inválido.")
                return redirect('estoque:sick')

            if novo_status == 'MANUTENCAO':

                sick.motivo = motivo_manutencao
                sick.previsao_retorno = previsao_retorno

                sick.ativo = True
                sick.data_resolucao = None
                sick.resolvido_por = None

            elif novo_status in ['ATIVO', 'INATIVO', 'SUCATA']:

                sick.ativo = False
                sick.data_resolucao = timezone.now()
                sick.resolvido_por = request.user

            #elif novo_status == 'MANUTENCAO':

            #    sick.ativo = True
            #    sick.data_resolucao = None

            sick.status_final = novo_status

            sick.save()

            equipamento = sick.equipamento
            equipamento.status = novo_status

            equipamento.save(update_fields=['status'])

            usuarios_destino = User.objects.filter(
                perfil__regionais=equipamento.regional,
                is_active=True
            ).exclude(
                id=request.user.id
            ).distinct()

            # Emitir comunicado para a base e admin
            if novo_status == 'MANUTENCAO':

                comunicado = Comunicado.objects.create(
                    titulo='Equipamento em manutenção',
                    mensagem=(
                        f'Regional: {equipamento.regional.nome}\n\n'
                        f'O equipamento "{equipamento.produto.descricao}" '
                        f'(Patrimônio: {equipamento.patrimonio or "N/A"}, '
                        f'Série: {equipamento.numero_serie or "N/A"}) '
                        f'foi encaminhado para manutenção.\n\n'
                        f'Previsão de retorno: {previsao_retorno or "Não informada"}.\n\n'
                        f'Motivo: {motivo_manutencao or "Não informado"}'
                    ),
                    tipo='MANUTENCAO',
                    criado_por=request.user,
                    empresa=equipamento.regional.empresa,
                )
                usuarios_destino = User.objects.filter(
                    perfil__regionais=equipamento.regional,
                    is_active=True
                ).exclude(
                    id=request.user.id
                )

                admins = User.objects.filter(
                    perfil__role='admin',
                    is_active=True
                )

                comunicado.usuarios.set(
                    (usuarios_destino | admins).distinct()
                )

            elif novo_status == 'ATIVO':

                comunicado = Comunicado.objects.create(
                    titulo='Equipamento pronto',
                    mensagem=(
                        f'Regional: {equipamento.regional.nome}\n\n'
                        f'O equipamento "{equipamento.produto.descricao}" '
                        f'(Patrimônio: {equipamento.patrimonio or "N/A"}, '
                        f'Série: {equipamento.numero_serie or "N/A"}) '
                        f'está disponível para retirada/utilização.'
                    ),
                    tipo='MANUTENCAO',
                    criado_por=request.user,
                    empresa=equipamento.regional.empresa,
                )
                usuarios_destino = User.objects.filter(
                    perfil__regionais=equipamento.regional,
                    is_active=True
                ).exclude(
                    id=request.user.id
                )

                admins = User.objects.filter(
                    perfil__role='admin',
                    is_active=True
                )

                comunicado.usuarios.set(
                    (usuarios_destino | admins).distinct()
                )


            elif novo_status == 'SUCATA':

                comunicado = Comunicado.objects.create(
                    titulo='Equipamento sucateado',
                    mensagem=(
                        f'O equipamento "{equipamento.produto.descricao}" '
                        f'(Patrimônio: {equipamento.patrimonio or "N/A"}) '
                        f'foi classificado como sucata após avaliação técnica.'
                    ),
                    tipo='MANUTENCAO',
                    criado_por=request.user,
                    empresa=equipamento.regional.empresa,
                )
                comunicado.usuarios.set(usuarios_destino)


            elif novo_status == 'INATIVO':

                comunicado = Comunicado.objects.create(
                    titulo='Equipamento inativado',
                    mensagem=(
                        f'Regional: {equipamento.regional.nome}\n\n'
                        f'O equipamento "{equipamento.produto.descricao}" '
                        f'(Patrimônio: {equipamento.patrimonio or "N/A"}, '
                        f'Série: {equipamento.numero_serie or "N/A"}) '
                        f'foi inativado.'
                    ),
                    tipo='MANUTENCAO',
                    criado_por=request.user,
                    empresa=equipamento.regional.empresa,
                )
                usuarios_destino = User.objects.filter(
                    perfil__regionais=equipamento.regional,
                    is_active=True
                ).exclude(
                    id=request.user.id
                )

                admins = User.objects.filter(
                    perfil__role='admin',
                    is_active=True
                )

                comunicado.usuarios.set(
                    (usuarios_destino | admins).distinct()
                )

            if novo_status == 'MANUTENCAO':
                tipo_acao = 'SICK_MANUTENCAO'

            elif novo_status == 'ATIVO':
                tipo_acao = 'SICK_RESOLVIDO'

            elif novo_status == 'SUCATA':
                tipo_acao = 'SICK_SUCATEADO'

            else:  # INATIVO
                tipo_acao = 'SICK_INATIVADO'

            Historico.objects.create(
                equipamento=equipamento,
                tipo_acao=tipo_acao,
                usuario=request.user,
                detalhes={
                    'sick_id': sick.id,
                    'status_final': novo_status,
                    'motivo_manutencao': motivo_manutencao,
                    'previsao_retorno': previsao_retorno or None,

                }
            )

            messages.success(
                request,
                f"Equipamento enviado para {novo_status}."
            )

            return redirect('estoque:sick')

    qs = Sick.objects.select_related(
        'equipamento',
        'equipamento__produto',
        'equipamento__regional',
        'resolvido_por'
    )

    if pode_realizar_manutencao_sick(request.user):

        sicks = qs

    else:

        if not perfil.regionais.exists():

            sicks = qs.none()

        else:

            sicks = qs.filter(
                equipamento__regional__in=perfil.regionais.all()
            )

    status_filter = request.GET.get('status', 'todos')
    produto_filter = request.GET.get('produto', '')
    categoria_filter = request.GET.get('categoria', '')
    regional_filter = request.GET.get('regional', '')

    if status_filter == 'pendentes':
        sicks = sicks.filter(
            ativo=True,
            status_final__isnull=True
        )

    elif status_filter == 'manutencao':
        sicks = sicks.filter(
            status_final='MANUTENCAO'
        )

    elif status_filter == 'inativos':
        sicks = sicks.filter(
            status_final='INATIVO'
        )

    elif status_filter == 'resolvidos':
        sicks = sicks.filter(
            status_final='ATIVO'
        )

    if categoria_filter:
        sicks = sicks.filter(
            equipamento__produto__categoria=categoria_filter
        )

    if produto_filter:
        sicks = sicks.filter(
            equipamento__produto_id=produto_filter
        )

    if regional_filter:
        sicks = sicks.filter(
            equipamento__regional_id=regional_filter
        )

    sicks = sicks.order_by('-data_ocorrencia')

    for sick in sicks:
        sick.historico_completo = sick.equipamento.sicks.all().order_by(
            '-data_ocorrencia'
        )

        sick.ultimo_sick = sick.equipamento.sicks.order_by(
            '-data_ocorrencia'
        ).first()


    total_pendentes = sicks.filter(
        ativo=True,
        status_final__isnull=True
    ).count()

    total_manutencao = sicks.filter(
        status_final='MANUTENCAO'
    ).count()

    total_inativos = sicks.filter(
        status_final='INATIVO'
    ).count()

    total_resolvidos = sicks.filter(
        status_final='ATIVO'
    ).count()

    if status_filter == 'todos':
        sicks = sicks.exclude(
            status_final='INATIVO'
        ).exclude(
            status_final='ATIVO'
        )
    categorias = Produto.objects.values_list(
        'categoria',
        flat=True
    ).distinct().order_by('categoria')

    produtos_lista = Produto.objects.filter(
        equipamento__sicks__in=sicks
    ).distinct().order_by('descricao')

    if pode_realizar_manutencao_sick(request.user):
        regionais = Base.objects.all().order_by('nome')
    else:
        regionais = perfil.regionais.all().order_by('nome')

    context = {

        'sicks': sicks,

        'total_sick': total_pendentes,
        'total_pendentes': total_pendentes,
        'total_resolvidos': total_resolvidos,
        'total_manutencao': total_manutencao,
        'total_inativos': total_inativos,
        'status_filter': status_filter,
        'produto_filter': produto_filter,
        'categoria_filter': categoria_filter,
        'regional_filter': regional_filter,
        'produtos_lista': produtos_lista,
        'categorias': categorias,
        'produtos_lista': produtos_lista,
        'regionais': regionais,
    }

    return render(
        request,
        'estoque/sick.html',
        context
    )

@login_required
@role_required('admin', 'gestor', 'operador')
def marcar_sick(request, equipamento_id):
    equipamento = get_object_or_404(Equipamento, id=equipamento_id)

    if request.method == 'POST':
        form = SickForm(
            request.POST,
            equipamento=equipamento,
            user=request.user
        )

        if form.is_valid():
            sick = form.save()

            equipamento.status = 'SICK'
            equipamento.save()

            Historico.objects.create(
                equipamento=equipamento,
                tipo_acao='SICK',
                usuario=request.user,
                detalhes={
                    'motivo': sick.motivo,
                    'categoria': sick.categoria
                }
            )

            messages.success(request, "Equipamento marcado como SICK.")
            return redirect('estoque:index')
    else:
        form = SickForm(equipamento=equipamento)

    return render(request, 'estoque/sick_form.html', {
        'form': form,
        'equipamento': equipamento
    })

@login_required
@require_POST
@role_required('admin', 'gestor', 'operador')
def marcar_sick_ajax(request, equipamento_id):
    equipamento = get_object_or_404(
        secure_queryset(
            Equipamento.objects.all(),
            request.user,
            'regional__empresa'
        ),
        id=equipamento_id
    )

    # Impedir marcação duplicada ou em status inválido
    if equipamento.status == "INATIVO":
        return JsonResponse({
            "success": False,
            "message": "Equipamento inativo não pode ser marcado como SICK."
        }, status=400)

    if equipamento.status == 'SICK':
        return JsonResponse({'erro': 'Já está em SICK'}, status=400)

    # Lê o motivo enviado pelo front-end (JSON)
    try:
        body = json.loads(request.body)
        motivo = body.get('motivo', '').strip()
    except json.JSONDecodeError:
        motivo = ''

    # Se não veio motivo ou está vazio, usa um valor padrão
    if not motivo:
        motivo = 'Via sistema'

    with transaction.atomic():
        equipamento.status = 'SICK'
        equipamento.save(update_fields=['status'])

        Sick.objects.create(
            equipamento=equipamento,
            motivo=motivo,
            categoria='OPERACIONAL',
        )

        Historico.objects.create(
            equipamento=equipamento,
            tipo_acao='STATUS',
            usuario=request.user,
            detalhes={'novo_status': 'SICK', 'motivo': motivo}
        )

    return JsonResponse({'sucesso': True})

@login_required
def detalhes_sick(request, sick_id):

    sick = get_object_or_404(
        Sick.objects.select_related(
            'equipamento',
            'equipamento__produto',
            'equipamento__regional',
            'resolvido_por'
        ),
        id=sick_id
    )

    historicos = Historico.objects.filter(
        equipamento=sick.equipamento
    ).order_by('-data')

    return render(
        request,
        'estoque/partials/modal_historico_sick.html',
        {
            'sick': sick,
            'historicos': historicos
        }
    )

# ----------------- HISTÓRICO -----------------
@login_required
@role_required('admin', 'gestor')
def historico_view(request):
    tipo_acao = request.GET.get('tipo_acao')
    equipamento_query = request.GET.get('equipamento')
    data_inicio = request.GET.get('data_inicio')
    data_fim = request.GET.get('data_fim')

    historico = Historico.objects.all().order_by('-data')

    if tipo_acao and tipo_acao != 'todos':
        historico = historico.filter(tipo_acao=tipo_acao)

    if equipamento_query:
        historico = historico.filter(
            Q(equipamento__numero_serie__icontains=equipamento_query) |
            Q(equipamento__patrimonio__icontains=equipamento_query) |
            Q(equipamento__produto__descricao__icontains=equipamento_query)
        )

    if data_inicio:
        historico = historico.filter(data__date__gte=data_inicio)

    if data_fim:
        historico = historico.filter(data__date__lte=data_fim)

    total_registros = historico.count()

    TIPO_ACAO_DICT = dict(Historico.TIPO_ACOES)

    acoes_agrupadas = [
        {
            'tipo_acao': item['tipo_acao'],
            'descricao': TIPO_ACAO_DICT.get(item['tipo_acao'], item['tipo_acao']),
            'total': item['total']
        }
        for item in (
            historico.values('tipo_acao')
            .annotate(total=Count('id'))
            .order_by('-total')
        )
    ]

    return render(request, 'estoque/historico.html', {
        'historicos': historico,
        'total_registros': total_registros,
        'acoes_agrupadas': acoes_agrupadas,
        'tipos_acao': Historico.TIPO_ACOES,
        'filtros': {
            'tipo_acao': tipo_acao or 'todos',
            'equipamento_query': equipamento_query or '',
            'data_inicio': data_inicio or '',
            'data_fim': data_fim or '',
        }
    })

@login_required
@role_required('admin', 'gestor')
def historico_detalhes_view(request, historico_id):
    historico = get_object_or_404(
        Historico.objects.select_related(
            'equipamento',
            'equipamento__produto',
            'usuario'
        ),
        id=historico_id
    )

    return render(request, 'estoque/historico_detalhes.html', {
        'historico': historico
    })

@login_required
@role_required('admin')
def exportar_historico_excel(request):

    regional_id = request.GET.get('regional')

    wb = Workbook()
    ws = wb.active
    ws.title = "Inventário"

    headers = [
        'Data Cadastro',
        'Regional',
        'Equipamento',
        'Tipo',
        'Número de Série',
        'Patrimônio',
        'Status',
        'Usuário'
    ]

    ws.append(headers)

    equipamentos = (
        Equipamento.objects
        .select_related(
            'produto',
            'regional'
        )
        .order_by(
            'regional__nome',
            'produto__descricao',
            'numero_serie'
        )
    )

    regional_nome = 'TODAS'

    if regional_id:

        equipamentos = equipamentos.filter(
            regional_id=regional_id
        )

        regional = Base.objects.filter(
            id=regional_id
        ).first()

        if regional:
            regional_nome = regional.nome

    # Primeiro histórico de criação de cada equipamento
    historicos_criacao = (
        Historico.objects
        .filter(
            tipo_acao='CRIACAO',
            equipamento__in=equipamentos
        )
        .select_related('usuario')
        .order_by('equipamento_id', 'data')
    )

    usuarios_por_equipamento = OrderedDict()

    for h in historicos_criacao:

        if h.equipamento_id not in usuarios_por_equipamento:
            usuarios_por_equipamento[h.equipamento_id] = h.usuario.username

    for eq in equipamentos:

        status = {
            'ATIVO': 'ATIVO',
            'MANUTENCAO': 'EM MANUTENÇÃO',
            'SICK': 'SICK',
            'EM_TRANSITO': 'EM TRANSFERÊNCIA',
            'RESERVADO_TRANSFERENCIA': 'EM TRANSFERÊNCIA',
            'BAIXA': 'INATIVO',
        }.get(eq.status, eq.status)

        usuario = usuarios_por_equipamento.get(
            eq.id,
            'Sistema'
        )

        ws.append([
            eq.data_cadastro.strftime('%d/%m/%Y %H:%M')
            if eq.data_cadastro else '',

            eq.regional.nome
            if eq.regional else '',

            eq.produto.descricao
            if eq.produto else '',

            eq.produto.get_categoria_display()
            if eq.produto else '',

            eq.numero_serie or '',

            eq.patrimonio or '',

            status,

            usuario,
        ])

    for column in ws.columns:

        max_length = 0
        column_letter = column[0].column_letter

        for cell in column:

            try:
                max_length = max(
                    max_length,
                    len(str(cell.value))
                )
            except Exception:
                pass

        ws.column_dimensions[column_letter].width = min(
            max_length + 3,
            50
        )

    filename = (
        f"inventario_equipamentos_{regional_nome}.xlsx"
        .replace(' ', '_')
    )

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

    response['Content-Disposition'] = (
        f'attachment; filename="{filename}"'
    )

    wb.save(response)

    return response

@login_required
@role_required('admin')
def exportar_historico_pdf(request):

    regional_id = request.GET.get('regional')

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="historico_equipamentos.pdf"'

    doc = SimpleDocTemplate(response)

    historicos = Historico.objects.select_related(
        'equipamento',
        'equipamento__produto',
        'usuario',
        'equipamento__regional'
    ).order_by('-data')

    if regional_id:
        historicos = historicos.filter(equipamento__regional_id=regional_id)

    data = [[
        "Data", "Regional", "Equipamento", "Serial", "Patrimônio", "Ação", "Usuário"
    ]]

    for h in historicos:
        data.append([
            h.data.strftime('%d/%m/%Y %H:%M'),
            getattr(h.equipamento.regional, "nome", "N/A"),
            h.equipamento.produto.descricao,
            h.equipamento.numero_serie,
            h.equipamento.patrimonio,
            h.get_tipo_acao_display(),
            h.usuario.username if h.usuario else "Sistema",
        ])

    table = Table(data)

    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
    ]))

    doc.build([table])
    return response

@login_required
def historico_equipamento_modal(request, equipamento_id):

    historico = (
        Historico.objects
        .select_related(
            'equipamento',
            'usuario',
            'equipamento__produto',
            'equipamento__regional'
        )
        .filter(equipamento_id=equipamento_id)
        .order_by('-data')
        .first()
    )

    if not historico:
        return HttpResponse("""
            <div class="alert alert-warning">
                Nenhum histórico encontrado para este equipamento.
            </div>
        """)

    return render(
        request,
        'estoque/partials/historico_detalhes.html',
        {
            'historico': historico,
            'equipamento': historico.equipamento,
            'is_admin': request.user.perfil.is_admin,
            'bases': Base.objects.all().order_by('nome'),
            'produtos': Produto.objects.all().order_by('categoria', 'descricao'),
            'status_choices': Equipamento.STATUS_CHOICES,
        }
    )

def historico_parcial(request, equipamento_id):
    historico = Historico.objects.filter(equipamento_id=equipamento_id).last()
    return render(request, 'estoque/partials/historico_detalhes.html', {
        'historico': historico
    })

# ----------------- BUSCA -----------------
@login_required
@role_required('admin', 'gestor')
def busca_avancada(request):
    query = request.GET.get('q', '')
    tipo_busca = request.GET.get('tipo', 'todos')

    resultados = None

    if query:
        if tipo_busca == 'serial':
            resultados = Equipamento.objects.filter(
                numero_serie__icontains=query
            ).select_related('produto')
        elif tipo_busca == 'patrimonio':
            resultados = Equipamento.objects.filter(
                patrimonio__icontains=query
            ).select_related('produto')
        elif tipo_busca == 'produto':
            resultados = Equipamento.objects.filter(
                produto__descricao__icontains=query
            ).select_related('produto')
        else:  # busca em todos os campos
            resultados = Equipamento.objects.filter(
                Q(numero_serie__icontains=query) |
                Q(patrimonio__icontains=query) |
                Q(produto__descricao__icontains=query)
            ).select_related('produto')

    return render(request, 'estoque/busca.html', {
        'resultados': resultados,
        'query': query,
        'tipo_busca': tipo_busca
    })

# ----------------- MENSAGENS  -----------------
@login_required
@role_required('admin')
def enviar_mensagem(request):

    empresas = Empresa.objects.all()

    usuarios = User.objects.select_related(
        'perfil'
    ).order_by('username')

    regionais = Base.objects.all().order_by('nome')

    if request.method == 'POST':

        titulo = request.POST.get('titulo')
        conteudo = request.POST.get('conteudo')

        enviar_para_todos = request.POST.get('todos') == 'on'

        empresa_id = request.POST.get('empresa')
        usuario_id = request.POST.get('usuario')

        regionais_ids = request.POST.getlist('regionais')

        arquivos = request.FILES.getlist('arquivos')

        if not titulo or not conteudo:

            messages.error(
                request,
                'Preencha título e mensagem.'
            )

            return redirect('estoque:enviar_mensagem')

        with transaction.atomic():

            mensagem = Mensagem.objects.create(
                titulo=titulo,
                conteudo=conteudo,
                enviado_por=request.user
            )

            destinatarios = User.objects.none()

            # TODOS
            if enviar_para_todos:

                destinatarios = User.objects.filter(
                    is_active=True
                )

                if empresa_id:

                    destinatarios = destinatarios.filter(
                        perfil__empresa_id=empresa_id
                    )

            elif regionais_ids:

                destinatarios = User.objects.filter(
                    perfil__regionais__id__in=regionais_ids,
                    is_active=True
                )

                if empresa_id:

                    destinatarios = destinatarios.filter(
                        perfil__empresa_id=empresa_id
                    )

            elif usuario_id:

                destinatarios = User.objects.filter(
                    id=usuario_id,
                    is_active=True
                )

            else:

                messages.error(
                    request,
                    'Selecione um destino.'
                )

                return redirect('estoque:enviar_mensagem')

            destinatarios = (
                    destinatarios |
                    User.objects.filter(id=request.user.id)
            ).distinct()

            for usuario in destinatarios:

                MensagemDestino.objects.create(
                    mensagem=mensagem,
                    usuario=usuario
                )

            for arquivo in arquivos:

                MensagemArquivo.objects.create(
                    mensagem=mensagem,
                    arquivo=arquivo,
                    nome_original=arquivo.name
                )

        messages.success(
            request,
            'Mensagem enviada com sucesso.'
        )

        return redirect('estoque:caixa_mensagens')

    return render(request, 'estoque/mensagens/enviar.html', {
        'empresas': empresas,
        'usuarios': usuarios,
        'regionais': regionais,
    })

@login_required
def caixa_mensagens(request):

    mensagens = (
        MensagemDestino.objects
        .select_related(
            'mensagem',
            'mensagem__enviado_por'
        )
        .prefetch_related(
            'mensagem__arquivos'
        )
        .filter(usuario=request.user)
        .order_by('-mensagem__enviado_em')
    )

    nao_lidas = mensagens.filter(lido=False).count()

    return render(request, 'estoque/mensagens/caixa.html', {
        'mensagens': mensagens,
        'nao_lidas': nao_lidas,
    })

@login_required
def visualizar_mensagem(request, destino_id):

    destino = get_object_or_404(
        MensagemDestino.objects.select_related(
            'mensagem',
            'mensagem__enviado_por'
        ).prefetch_related(
            'mensagem__arquivos'
        ),
        id=destino_id,
        usuario=request.user
    )

    if not destino.lido:

        destino.lido = True
        destino.data_leitura = timezone.now()
        destino.save(
            update_fields=[
                'lido',
                'data_leitura'
            ]
        )

    return render(
        request,
        'estoque/mensagens/detalhe.html',
        {
            'destino': destino,
            'mensagem': destino.mensagem,
        }
    )

@login_required
@role_required('admin')
def criar_comunicado(request):

    if request.method == 'POST':

        titulo = request.POST.get('titulo')
        mensagem = request.POST.get('mensagem')
        tipo = request.POST.get('tipo')

        empresa_id = request.POST.get('empresa')

        enviar_para_todos = (
            request.POST.get('enviar_para_todos') == 'on'
        )

        regionais_ids = request.POST.getlist('regionais')

        expira_em = request.POST.get('expira_em')

        data_expiracao = None

        if expira_em:

            try:

                data = parse_date(expira_em)

                if not data:
                    raise ValueError()

                data_expiracao = timezone.make_aware(
                    datetime.combine(data, time.max)
                )

            except Exception:

                messages.error(
                    request,
                    'Data de expiração inválida.'
                )

                return redirect('estoque:criar_comunicado')

        comunicado = Comunicado.objects.create(
            titulo=titulo,
            mensagem=mensagem,
            tipo=tipo,
            criado_por=request.user,
            empresa_id=empresa_id if empresa_id else None,
            enviar_para_todos=enviar_para_todos,
            expira_em=data_expiracao
        )

        if enviar_para_todos:

            usuarios = User.objects.filter(
                is_active=True
            )

            if empresa_id:
                usuarios = usuarios.filter(
                    perfil__empresa_id=empresa_id
                )

            usuarios = (
                    usuarios |
                    User.objects.filter(id=request.user.id)
            ).distinct()

            comunicado.usuarios.set(usuarios)



        elif regionais_ids:

            usuarios = User.objects.filter(

                perfil__regionais__id__in=regionais_ids,

                is_active=True

            )

            if empresa_id:
                usuarios = usuarios.filter(

                    perfil__empresa_id=empresa_id

                )

            usuarios = (

                    usuarios |

                    User.objects.filter(id=request.user.id)

            ).distinct()

            comunicado.usuarios.set(usuarios)

        for arquivo in request.FILES.getlist('arquivos'):

            ComunicadoArquivo.objects.create(
                comunicado=comunicado,
                arquivo=arquivo
            )

        messages.success(
            request,
            'Comunicado enviado com sucesso.'
        )

        return redirect('estoque:caixa_comunicados')

    empresas = Empresa.objects.all().order_by('nome')

    regionais = Base.objects.all().order_by('nome')

    return render(
        request,
        'estoque/comunicados/criar.html',
        {
            'empresas': empresas,
            'regionais': regionais,
            'tipos': Comunicado.TIPOS
        }
    )

@login_required
def caixa_comunicados(request):

    comunicados = (
        Comunicado.objects
        .filter(
            ativo=True
        )
        .exclude(
            comunicadooculto__usuario=request.user
        )
    )

    comunicados = comunicados.filter(
        Q(expira_em__isnull=True) |
        Q(expira_em__gt=timezone.now())
    )

    comunicados = comunicados.filter(
        Q(enviar_para_todos=True) |
        Q(usuarios=request.user)
    ).distinct().order_by('-criado_em')

    return render(
        request,
        'estoque/comunicados/caixa.html',
        {
            'comunicados': comunicados
        }
    )

@login_required
def detalhe_comunicado(request, comunicado_id):

    perfil = request.user.perfil

    comunicado = get_object_or_404(

        Comunicado.objects.prefetch_related(
            'leituras__usuario',
            'usuarios'
        ).filter(

            Q(enviar_para_todos=True) |
            Q(usuarios=request.user) |
            Q(empresa=perfil.empresa)

        ).distinct(),

        id=comunicado_id
    )

    # REGISTRA LEITURA
    ComunicadoLeitura.objects.get_or_create(
        comunicado=comunicado,
        usuario=request.user
    )

   # ANALYTICS (ADMIN)
    leituras = []
    usuarios_nao_leram = []

    total_enviados = 0
    total_lidos = 0
    percentual_lido = 0

    if perfil.role == 'admin':

        # DESTINATÁRIOS
        if comunicado.enviar_para_todos:

            destinatarios = User.objects.filter(
                is_active=True
            )

            if comunicado.empresa:

                destinatarios = destinatarios.filter(
                    perfil__empresa=comunicado.empresa
                )

        else:

            destinatarios = comunicado.usuarios.all()

        total_enviados = destinatarios.count()

        # LEITURAS
        leituras = comunicado.leituras.select_related(
            'usuario',
            'usuario__perfil'
        ).order_by('-lido_em')

        usuarios_leram_ids = leituras.values_list(
            'usuario_id',
            flat=True
        )

        total_lidos = leituras.count()

        # NÃO LERAM
        usuarios_nao_leram = destinatarios.select_related(
            'perfil'
        ).exclude(
            id__in=usuarios_leram_ids
        )

        # PERCENTUAL
        if total_enviados > 0:

            percentual_lido = int(
                (total_lidos / total_enviados) * 100
            )

    return render(
        request,
        'estoque/comunicados/detalhe.html',
        {
            'comunicado': comunicado,

            'leituras': leituras,

            'usuarios_nao_leram': usuarios_nao_leram,

            'total_enviados': total_enviados,

            'total_lidos': total_lidos,

            'percentual_lido': percentual_lido,
        }
    )

@login_required
@require_POST
def ocultar_comunicado(request, comunicado_id):

    comunicado = get_object_or_404(
        Comunicado,
        id=comunicado_id
    )

    if not comunicado.permitir_limpar:
        messages.error(request, 'Este comunicado não pode ser removido.')
        return redirect('estoque:caixa_comunicados')

    ComunicadoOculto.objects.get_or_create(
        comunicado=comunicado,
        usuario=request.user
    )

    messages.success(request, 'Comunicado removido da sua caixa.')

    return redirect('estoque:caixa_comunicados')

@login_required
def caixa_alertas(request):

    alertas = request.user.alertas.all()

    return render(request, 'estoque/alertas/caixa.html', {
        'alertas': alertas
    })

@login_required
def ler_alerta(request, alerta_id):

    alerta = get_object_or_404(
        Alerta,
        id=alerta_id,
        usuario=request.user
    )

    alerta.lido = True
    alerta.save(update_fields=['lido'])

    if alerta.link:
        return redirect(alerta.link)

    return redirect('estoque:caixa_alertas')


# ----------------- EMPRÉSTIMOS --------------------
def _usuario_tem_acesso_emprestimo(user, emprestimo):
    perfil = user.perfil
    if perfil.is_admin:
        return True

    bases = perfil.regionais.all()

    return (
        emprestimo.regional_origem in bases
        or emprestimo.regional_destino in bases
    )

def _usuario_e_destino(user, emprestimo):
    perfil = user.perfil

    return (
        perfil.is_admin
        or emprestimo.regional_destino in perfil.regionais.all()
    )

def _usuario_e_origem(user, emprestimo):

    perfil = user.perfil

    return (
        perfil.is_admin
        or emprestimo.regional_origem in perfil.regionais.all()
    )

@login_required
def lista_emprestimos(request):

    perfil = request.user.perfil

    emprestimos = (
        Emprestimo.objects
        .select_related(
            'regional_origem',
            'regional_destino',
            'solicitado_por',
        )
        .prefetch_related(
            'itens',
        )
        .order_by('-criado_em')
    )

    if not perfil.is_admin:

        emprestimos = emprestimos.filter(
            Q(regional_origem__in=perfil.regionais.all())
            |
            Q(regional_destino__in=perfil.regionais.all())
        ).distinct()

    return render(
        request,
        'estoque/emprestimos/lista.html',
        {
            'emprestimos': emprestimos,
        }
    )

@login_required
@transaction.atomic
def criar_emprestimo(request):

    perfil = request.user.perfil

    regionais_usuario = perfil.regionais.select_related(
        'grupo_regional'
    )

    regionais_destino = Base.objects.select_related(
        'grupo_regional'
    )

    equipamentos = (
        Equipamento.objects
        .filter(
            status='ATIVO',
            regional__in=regionais_usuario
        )
        .select_related(
            'produto',
            'regional',
        )
        .order_by(
            'produto__descricao',
            'numero_serie',
        )
    )

    produtos_lista = (
        Produto.objects
        .filter(
            equipamento__status='ATIVO',
            equipamento__regional__in=regionais_usuario
        )
        .distinct()
        .order_by('descricao')
    )

    if request.method == 'POST':

        regional_origem = get_object_or_404(
            Base,
            id=request.POST.get('regional_origem')
        )

        regional_destino = get_object_or_404(
            Base,
            id=request.POST.get('regional_destino')
        )

        motivo = request.POST.get('motivo')

        data_prevista = request.POST.get(
            'data_prevista_devolucao'
        )

        equipamentos_ids = request.POST.getlist(
            'equipamentos'
        )

        if regional_origem not in regionais_usuario:

            messages.error(
                request,
                'Você não possui acesso à base de origem.'
            )

            return redirect(
                'estoque:criar_emprestimo'
            )

        if (
            regional_origem.grupo_regional
            != regional_destino.grupo_regional
        ):

            messages.error(
                request,
                'As bases devem pertencer ao mesmo grupo.'
            )

            return redirect(
                'estoque:criar_emprestimo'
            )

        if not equipamentos_ids:

            messages.warning(
                request,
                'Selecione ao menos um equipamento.'
            )

            return redirect(
                'estoque:criar_emprestimo'
            )

        equipamentos_selecionados = (
            Equipamento.objects
            .filter(
                id__in=equipamentos_ids,
                regional=regional_origem,
                status='ATIVO',
            )
        )

        try:

            emprestimo = EmprestimoService.criar(
                base_origem=regional_origem,
                base_destino=regional_destino,
                user=request.user,
                motivo=motivo,
                data_prevista=data_prevista,
                equipamentos=equipamentos_selecionados,
            )

            messages.success(
                request,
                f'Empréstimo {emprestimo.protocolo} criado com sucesso.'
            )

            return redirect(
                'estoque:detalhe_emprestimo',
                emprestimo.id
            )

        except ValidationError as e:

            messages.error(
                request,
                str(e)
            )

            return redirect(
                'estoque:criar_emprestimo'
            )

    context = {
        'regionais_usuario': regionais_usuario,
        'regionais_destino': regionais_destino,
        'categorias': Produto.CATEGORIAS,
        'equipamentos': equipamentos,
        'produtos_lista': produtos_lista,
    }

    return render(
        request,
        'estoque/emprestimos/criar.html',
        context
    )

@login_required
def detalhe_emprestimo(request, emprestimo_id):

    emprestimo = get_object_or_404(

        Emprestimo.objects
        .select_related(
            'regional_origem',
            'regional_destino',
            'solicitado_por',
        )
        .prefetch_related(
            'itens',
            'itens__equipamento',
            'itens__equipamento__produto',
        ),

        id=emprestimo_id
    )

    if not _usuario_tem_acesso_emprestimo(
        request.user,
        emprestimo
    ):
        raise PermissionDenied()

    possui_itens_para_devolver = (
        emprestimo.itens.filter(
            status__in=[
                'RECEBIDO',
                'DIVERGENCIA',
            ]
        ).exists()
    )

    possui_itens_para_confirmar = (
        emprestimo.itens.filter(
            status__in=[
                'DEVOLVIDO',
                'DIVERGENCIA',
            ]
        ).exists()
    )

    context = {

        'emprestimo': emprestimo,

        'pode_receber': (

            emprestimo.status ==
            'AGUARDANDO_RECEBIMENTO'

            and

            _usuario_e_destino(
                request.user,
                emprestimo
            )
        ),

        'pode_devolver': (

            emprestimo.status == 'EMPRESTADO'

            and

            possui_itens_para_devolver

            and

            _usuario_e_destino(
                request.user,
                emprestimo
            )
        ),

        'pode_confirmar_devolucao': (

            emprestimo.status in [
                'AGUARDANDO_CONFIRMACAO_DEVOLUCAO',
                'EMPRESTADO',
            ]

            and

            possui_itens_para_confirmar

            and

            _usuario_e_origem(
                request.user,
                emprestimo
            )
        ),
    }

    return render(
        request,
        'estoque/emprestimos/detalhe.html',
        context
    )

@login_required
@transaction.atomic
def receber_emprestimo(request, emprestimo_id):

    emprestimo = get_object_or_404(
        Emprestimo.objects.prefetch_related(
            'itens',
            'itens__equipamento',
        ),
        id=emprestimo_id
    )

    perfil = request.user.perfil

    if (
        not perfil.is_admin
        and emprestimo.regional_destino
        not in perfil.regionais.all()
    ):
        raise PermissionDenied()

    if emprestimo.status != 'AGUARDANDO_RECEBIMENTO':

        messages.warning(
            request,
            'Este empréstimo não está aguardando recebimento.'
        )

        return redirect(
            'estoque:detalhe_emprestimo',
            emprestimo.id
        )

    if request.method == 'POST':

        recebidos = request.POST.getlist(
            'itens_recebidos'
        )

        EmprestimoService.receber(
            emprestimo,
            recebidos,
            request.user,
        )

        messages.success(
            request,
            'Recebimento confirmado.'
        )

        return redirect(
            'estoque:detalhe_emprestimo',
            emprestimo.id
        )

    return render(
        request,
        'estoque/emprestimos/receber.html',
        {
            'emprestimo': emprestimo,
        }
    )

@login_required
@transaction.atomic
def devolver_emprestimo(request, emprestimo_id):

    emprestimo = get_object_or_404(
        Emprestimo.objects.prefetch_related(
            'itens',
            'itens__equipamento',
        ),
        id=emprestimo_id
    )

    perfil = request.user.perfil

    if (
        not perfil.is_admin
        and emprestimo.regional_destino
        not in perfil.regionais.all()
    ):
        raise PermissionDenied()

    if emprestimo.status != 'EMPRESTADO':

        messages.warning(
            request,
            'Este empréstimo não pode ser devolvido.'
        )

        return redirect(
            'estoque:detalhe_emprestimo',
            emprestimo.id
        )

    if request.method == 'POST':

        devolvidos = request.POST.getlist(
            'itens_devolvidos'
        )

        EmprestimoService.devolver(
            emprestimo,
            devolvidos,
            request.user,
        )

        messages.success(
            request,
            'Devolução registrada.'
        )

        return redirect(
            'estoque:detalhe_emprestimo',
            emprestimo.id
        )

    return render(
        request,
        'estoque/emprestimos/devolver.html',
        {
            'emprestimo': emprestimo,
        }
    )

@login_required
@transaction.atomic
def receber_devolucao_emprestimo(request, emprestimo_id):

    emprestimo = get_object_or_404(
        Emprestimo.objects.prefetch_related(
            'itens',
            'itens__equipamento',
        ),
        id=emprestimo_id
    )

    if not _usuario_e_origem(
        request.user,
        emprestimo
    ):
        raise PermissionDenied()

    if (
        emprestimo.status !=
        'AGUARDANDO_CONFIRMACAO_DEVOLUCAO'
    ):

        messages.warning(
            request,
            'Esta devolução não está aguardando confirmação.'
        )

        return redirect(
            'estoque:detalhe_emprestimo',
            emprestimo.id
        )

    if request.method == 'POST':

        itens_confirmados = request.POST.getlist(
            'itens_confirmados'
        )

        EmprestimoService.confirmar_devolucao(
            emprestimo,
            itens_confirmados,
            request.user,
        )

        messages.success(
            request,
            'Devolução confirmada.'
        )

        return redirect(
            'estoque:detalhe_emprestimo',
            emprestimo.id,
        )

    return render(
        request,
        'estoque/emprestimos/receber_devolucao.html',
        {
            'emprestimo': emprestimo,
        }
    )


# ----------------- TRANSFERÊNCIAS -----------------

@login_required
@role_required('admin', 'gestor')
def painel_alocacao(request, solicitacao_id):

    solicitacao = get_object_or_404(
        Solicitacao.objects.prefetch_related('itens'),
        id=solicitacao_id
    )

    itens_solicitados = solicitacao.itens.all()

    if request.method == "POST":

        transferencias_criadas = 0

        with transaction.atomic():

            for item in itens_solicitados:

                prefixo = f"alocacao_{item.id}_"

                campos_item = {
                    k: v
                    for k, v in request.POST.items()
                    if k.startswith(prefixo)
                }

                for key, valor in campos_item.items():

                    try:
                        quantidade = int(valor or 0)
                    except ValueError:
                        continue

                    if quantidade <= 0:
                        continue

                    try:
                        _, _, regional_id, produto_id = key.split("_")
                    except ValueError:
                        continue

                    disponiveis = Equipamento.objects.filter(
                        regional_id=regional_id,
                        produto_id=produto_id,
                        status='ATIVO'
                    ).count()

                    if disponiveis < quantidade:

                        messages.warning(
                            request,
                            (
                                f'Estoque insuficiente para '
                                f'o produto selecionado.'
                            )
                        )

                        continue

                    alocacao = AlocacaoSolicitacaoItem.objects.create(
                        item=item,
                        regional_origem_id=regional_id,
                        produto_id=produto_id,
                        quantidade=quantidade
                    )

                    Transferencia.objects.create(
                        protocolo=str(uuid4())[:8].upper(),
                        regional_origem_id=regional_id,
                        regional_destino=solicitacao.regional_solicitante,
                        solicitado_por=request.user,
                        status='PENDENTE',
                        alocacao=alocacao
                    )

                    transferencias_criadas += 1

            if transferencias_criadas > 0:

                solicitacao.status = 'EM_TRANSFERENCIA'

                solicitacao.save(
                    update_fields=['status']
                )

                # COMUNICADO PARA O SOLICITANTE
                comunicado = Comunicado.objects.create(

                    titulo=(
                        f'Solicitação #{solicitacao.id} aprovada'
                    ),

                    mensagem=(

                        f'Sua solicitação foi aprovada.\n\n'

                        f'As transferências dos equipamentos '
                        f'já foram iniciadas.'
                    ),

                    tipo='OPERACIONAL',

                    criado_por=request.user,

                    ativo=True
                )

                comunicado.usuarios.add(
                    solicitacao.criado_por
                )

                messages.success(
                    request,
                    f'{transferencias_criadas} transferência(s) criada(s).'
                )

            else:

                messages.warning(
                    request,
                    'Nenhuma transferência foi criada.'
                )

        return redirect('estoque:caixa_separacao')

    itens_contexto = []

    for item in itens_solicitados:

        regionais_data = []

        regionais = (
            Equipamento.objects
            .filter(
                produto__categoria=item.categoria
            )
            .exclude(
                regional=solicitacao.regional_solicitante
            )
            .values(
                'regional__id',
                'regional__nome'
            )
            .distinct()
            .order_by('regional__nome')
        )

        for regional in regionais:

            equipamentos = (
                Equipamento.objects
                .select_related(
                    'produto',
                    'regional'
                )
                .filter(
                    produto__categoria=item.categoria,
                    regional_id=regional['regional__id']
                )
            )

            produtos_map = {}

            for eq in equipamentos:

                chave = eq.produto.id

                if chave not in produtos_map:

                    produtos_map[chave] = {
                        "produto_id": eq.produto.id,
                        "produto": eq.produto.descricao,
                        "disponivel": 0,
                        "reservados": 0,
                        "sick": 0,
                    }

                if eq.status == "ATIVO":

                    produtos_map[chave]["disponivel"] += 1

                elif eq.status == "TRANSFERENCIA":

                    produtos_map[chave]["reservados"] += 1

                elif eq.status == "SICK":

                    produtos_map[chave]["sick"] += 1

            produtos_lista = sorted(
                produtos_map.values(),
                key=lambda x: (
                    -x['disponivel'],
                    x['produto']
                )
            )

            total_disponivel = sum(
                p['disponivel']
                for p in produtos_lista
            )

            regionais_data.append({
                "regional_id": regional['regional__id'],
                "regional": regional['regional__nome'],
                "total": total_disponivel,
                "produtos": produtos_lista
            })

        regionais_data = sorted(
            regionais_data,
            key=lambda x: -x['total']
        )

        itens_contexto.append({
            "id": item.id,
            "categoria": item.categoria,
            "pendente": item.pendente,
            "regionais": regionais_data
        })

    return render(
        request,
        "estoque/alocacao/painel.html",
        {
            "solicitacao": solicitacao,
            "itens": itens_contexto
        }
    )

@login_required
def dashboard_gestor(request):

    from .services.estoque_service import get_estoque_por_produto

    estoque = get_estoque_por_produto()

    resumo = {}

    for produto in estoque.values():
        cat = produto['categoria']

        if cat not in resumo:
            resumo[cat] = 0

        resumo[cat] += sum(r['total'] for r in produto['regionais'])

    return render(request, 'gestor/dashboard.html', {
        'resumo': resumo
    })

@login_required
@login_required
@role_required('admin', 'gestor')
def caixa_solicitacoes(request):

    perfil = request.user.perfil

    solicitacoes = (
        Solicitacao.objects
        .select_related(
            'regional_solicitante',
            'criado_por'
        )
        .prefetch_related(
            'itens'
        )
        .filter(
            status='PENDENTE'
        )
        .order_by('-id')
    )

    if perfil.role != 'admin':

        solicitacoes = solicitacoes.filter(
            regional_solicitante__in=perfil.regionais.all()
        )

    return render(
        request,
        'estoque/solicitacoes/caixa.html',
        {
            'solicitacoes': solicitacoes
        }
    )
#@login_required
#@role_required('admin')
#def caixa_solicitacoes(request):
#    solicitacoes = (
#        Solicitacao.objects
#        .select_related('criado_por', 'regional_solicitante')
#        .prefetch_related('itens__produto')
#        .order_by('-data_criacao')
#    )

#    pendentes = solicitacoes.filter(status='PENDENTE')
#    aprovadas = solicitacoes.filter(status='APROVADO')

#    return render(request, 'estoque/solicitacoes/caixa.html', {
#        'pendentes': pendentes,
#        'aprovadas': aprovadas,
#    })

@login_required
def transferencia_selecionados(request, id):

    transferencia = get_object_or_404(
        Transferencia.objects.prefetch_related(
            'itens__equipamento__produto'
        ),
        id=id
    )

    return render(
        request,
        'estoque/transferencia/selecionados.html',
        {
            'transferencia': transferencia
        }
    )

@login_required
@role_required('gestor', 'operador', 'admin')
def caixa_separacao(request):

    perfil = request.user.perfil

    transferencias = (
        Transferencia.objects
        .select_related(
            'regional_origem',
            'regional_destino'
        )
        .prefetch_related(
            'itens',
            'itens__equipamento'
        )
    )

    if perfil.role != 'admin':

        transferencias = transferencias.filter(
            regional_origem__in=perfil.regionais.all()
        )

    transferencias = transferencias.filter(
        status='PENDENTE'
    ).order_by('-id')

    return render(
        request,
        'estoque/caixa_separacao.html',
        {
            'transferencias': transferencias
        }
    )

@login_required
def caixa_transferencias(request):

    perfil = request.user.perfil

    transferencias = Transferencia.objects.filter(
        regional_destino__in=perfil.regionais.all(),
        status='EM_TRANSITO'
    ).order_by('-id')

    return render(request, 'estoque/caixa_transferencias.html', {
        'transferencias': transferencias
    })

@login_required
@role_required('gestor', 'operador', 'admin')
def separar_transferencia(request, transferencia_id):

    transferencia = get_object_or_404(
        Transferencia.objects.select_related(
            'regional_origem',
            'regional_destino',
            'alocacao__item'
        ),
        id=transferencia_id
    )

    if request.method == 'POST':

        equipamentos_ids = request.POST.getlist('equipamentos')

        if not equipamentos_ids:
            messages.error(request, 'Selecione equipamentos.')
            return redirect(
                'estoque:separar_transferencia',
                transferencia_id=transferencia.id
            )

        with transaction.atomic():

            equipamentos = Equipamento.objects.filter(
                id__in=equipamentos_ids,
                regional=transferencia.regional_origem,
                status='ATIVO'
            ).select_for_update()

            for eq in equipamentos:

                TransferenciaItem.objects.create(
                    transferencia=transferencia,
                    equipamento=eq
                )

                eq.status = 'TRANSFERENCIA'
                eq.save(update_fields=['status'])

            transferencia.status = 'EM_TRANSITO'
            transferencia.data_envio = timezone.now()
            transferencia.save()

            usuarios = User.objects.filter(
                perfil__regionais=transferencia.regional_destino
            ).distinct()

            for usuario in usuarios:

                Notificacao.objects.get_or_create(
                    usuario=usuario,
                    transferencia=transferencia,
                    tipo='TRANSFERENCIA',
                    evento='EM_TRANSFERENCIA',
                    defaults={
                        'mensagem': (
                            f'Transferência #{transferencia.id} '
                            f'em trânsito.'
                        ),
                        'link': f'/transferencias/{transferencia.id}/'
                    }
                )

        messages.success(request, 'Transferência enviada.')

        return redirect('estoque:caixa_separacao')

    equipamentos = Equipamento.objects.filter(
        regional=transferencia.regional_origem,
        produto_id__in=[
            p['produto_id']
            for p in transferencia.alocacao.item.alocacoes.values()
        ],
        status='ATIVO'
    )

    return render(
        request,
        'estoque/transferencia/separar.html',
        {
            'transferencia': transferencia,
            'equipamentos': equipamentos
        }
    )

def notificar_transferencia(usuario, transferencia, evento):
    Notificacao.objects.get_or_create(
        usuario=usuario,
        transferencia=transferencia,
        tipo='TRANSFERENCIA',
        evento=evento,
        defaults={
            'mensagem': f"Transferência {evento.lower()}",
            'link': f"/transferencias/{transferencia.id}/"
        }
    )

def pode_transferir(equipamento):

    if equipamento.status == 'SICK':
        return False, 'SICK'

    if Transferencia.objects.filter(
        itens__equipamento=equipamento,
        status__in=['PENDENTE', 'EM_TRANSITO']
    ).exists():

        return False, 'PENDENTE'

    return True, None

@login_required
@role_required('admin', 'gestor')
def criar_solicitacao(request):

    perfil = request.user.perfil

    if request.method == 'POST':

        motivo = request.POST.get('motivo')
        regional_id = request.POST.get('regional')

        categorias = request.POST.getlist('categoria')
        quantidades = request.POST.getlist('quantidade')

        if not motivo:
            messages.error(
                request,
                'Informe o motivo da solicitação.'
            )
            return redirect('estoque:criar_solicitacao')

        regional = perfil.regionais.filter(
            id=regional_id
        ).first()

        if not regional:
            messages.error(
                request,
                'Selecione uma regional válida.'
            )
            return redirect('estoque:criar_solicitacao')

        if not categorias:
            messages.error(
                request,
                'Adicione pelo menos um item.'
            )
            return redirect('estoque:criar_solicitacao')

        try:
            with transaction.atomic():

                solicitacao = Solicitacao.objects.create(
                    motivo=motivo,
                    regional_solicitante=regional,
                    criado_por=request.user
                )

                itens_validos = 0

                for categoria, qtd in zip(categorias, quantidades):

                    if not categoria or not qtd:
                        continue

                    qtd = int(qtd)

                    if qtd <= 0:
                        continue

                    SolicitacaoItem.objects.create(
                        solicitacao=solicitacao,
                        categoria=categoria,
                        quantidade=qtd
                    )

                    itens_validos += 1

                if itens_validos == 0:
                    raise ValueError(
                        'Nenhum item válido informado.'
                    )

        except Exception as e:

            messages.error(
                request,
                f'Erro ao criar solicitação: {str(e)}'
            )

            return redirect(
                'estoque:criar_solicitacao'
            )

        messages.success(
            request,
            'Solicitação criada com sucesso!'
        )

        return redirect(
            'estoque:caixa_solicitacoes'
        )

    return render(
        request,
        'estoque/solicitacoes/criar.html',
        {
            'regionais': perfil.regionais.order_by('nome')
        }
    )

@login_required
@role_required('admin', 'gestor')
def finalizar_transferencia(transferencia, user):
    equipamento = transferencia.equipamento

    transferencia.status = 'RECEBIDO'
    transferencia.recebido_por = user
    transferencia.data_recebimento = timezone.now()
    transferencia.save()

    equipamento.regional = transferencia.regional_destino
    equipamento.status = 'ATIVO'
    equipamento.save(update_fields=['regional', 'status'])

    Historico.objects.create(
        equipamento=equipamento,
        tipo_acao='TRANSFERENCIA',
        usuario=user,
        detalhes={
            'origem': transferencia.regional_origem.nome,
            'destino': transferencia.regional_destino.nome,
        }
    )

@login_required
@role_required('gestor', 'operador', 'admin')
def transferencia_detalhe(request, id):
    transferencia = get_object_or_404(
        Transferencia.objects
        .select_related(
            'regional_origem',
            'regional_destino',
            'solicitado_por',
            'alocacao',
            'alocacao__item',
            'alocacao__produto',
        )
        .prefetch_related(
            'itens__equipamento__produto'
        ),
        id=id
    )

    perfil = request.user.perfil

    if (
        perfil.role != 'admin'
        and not perfil.regionais.filter(id=transferencia.regional_origem.id).exists()
    ):
        messages.error(request, 'Sem permissão.')
        return redirect('estoque:caixa_separacao')

    alocacao = transferencia.alocacao

    if not alocacao:
        messages.error(
            request,
            'Transferência sem alocação.'
        )
        return redirect('estoque:caixa_separacao')

    item_solicitacao = alocacao.item

    produto_id = alocacao.produto_id

    categoria = item_solicitacao.categoria

    quantidade = alocacao.quantidade
    equipamentos_disponiveis = (
        Equipamento.objects
        .filter(
            regional=transferencia.regional_origem,
            status='ATIVO',
            produto_id=produto_id
        )
        .select_related('produto')
    )

    if request.method == 'POST':

        ids = request.POST.getlist('equipamentos')

        if len(ids) != quantidade:
            messages.error(
                request,
                f'Selecione exatamente {quantidade} equipamento(s).'
            )
            return redirect('estoque:transferencia_detalhe', id=transferencia.id)

        with transaction.atomic():

            equipamentos = Equipamento.objects.select_for_update().filter(
                id__in=ids,
                regional=transferencia.regional_origem,
                status='ATIVO'
            )

            if equipamentos.count() != quantidade:
                messages.error(
                    request,
                    'Alguns equipamentos não estão disponíveis.'
                )
                return redirect('estoque:transferencia_detalhe', id=transferencia.id)

            for eq in equipamentos:

                TransferenciaItem.objects.create(
                    transferencia=transferencia,
                    equipamento=eq
                )

                eq.status = 'TRANSFERENCIA'
                eq.save(update_fields=['status'])

                Historico.objects.create(
                    equipamento=eq,
                    tipo_acao='TRANSFERENCIA',
                    usuario=request.user,
                    detalhes={
                        'origem': transferencia.regional_origem.nome,
                        'destino': transferencia.regional_destino.nome,
                        'transferencia_id': transferencia.id
                    }
                )

            transferencia.status = 'EM_TRANSITO'
            transferencia.data_envio = timezone.now()
            transferencia.save(update_fields=['status', 'data_envio'])

            usuarios_destino = User.objects.filter(
                perfil__regionais=transferencia.regional_destino
            ).distinct()

            notificacoes = []
            for usuario in usuarios_destino:
                notificacoes.append(
                    Notificacao(
                        usuario=usuario,
                        transferencia=transferencia,
                        tipo='TRANSFERENCIA',
                        evento='EM_TRANSFERENCIA',
                        mensagem=(
                            f'Transferência #{transferencia.id} enviada '
                            f'por {transferencia.regional_origem.nome}'
                        ),
                        link=f'/transferencias/{transferencia.id}/'
                    )
                )

            Notificacao.objects.bulk_create(notificacoes)

        messages.success(request, 'Equipamentos separados e transferência enviada.')
        return redirect('estoque:caixa_separacao')

    alocacao = transferencia.alocacao

    if not alocacao:
        messages.error(request, 'Transferência sem alocação.')
        return redirect('estoque:caixa_separacao')

    itens = [{
        "produto": alocacao.produto,
        "quantidade": alocacao.quantidade,
        "regional_origem": transferencia.regional_origem,
        "categoria": alocacao.item.categoria
    }]

    return render(request, 'estoque/transferencia/detalhe.html', {
        'transferencia': transferencia,
        'itens': itens,
        'equipamentos_disponiveis': equipamentos_disponiveis,
        'quantidade_necessaria': alocacao.quantidade,
        'categoria': alocacao.item.categoria,
        'produto': alocacao.produto,
        'regional_origem': transferencia.regional_origem,
    })

@login_required
@role_required('admin')
@require_POST
def recusar_solicitacao(request, solicitacao_id):

    solicitacao = get_object_or_404(
        Solicitacao,
        id=solicitacao_id,
        status='PENDENTE'
    )

    motivo = request.POST.get('motivo_recusa')

    if not motivo:

        messages.error(
            request,
            'Informe o motivo da recusa.'
        )

        return redirect(
            'estoque:caixa_solicitacoes'
        )

    solicitacao.status = 'REJEITADO'

    solicitacao.recusado_por = request.user

    solicitacao.data_recusa = timezone.now()

    solicitacao.motivo_recusa = motivo

    solicitacao.save()

    # NOTIFICAÇÃO
    Notificacao.objects.create(

        usuario=solicitacao.criado_por,

        solicitacao=solicitacao,

        tipo='SOLICITACAO',

        evento='REJEITADA',

        mensagem=(
            f'Solicitação #{solicitacao.id} recusada.'
        )
    )

    # MENSAGEM DETALHADA
    comunicado = Comunicado.objects.create(

        titulo=f'Solicitação #{solicitacao.id} recusada',

        mensagem=(

            f'Sua solicitação foi recusada.\n\n'

            f'Motivo da recusa:\n'
            f'{motivo}'
        ),

        tipo='URGENTE',

        criado_por=request.user,

        ativo=True
    )

    comunicado.usuarios.add(
        solicitacao.criado_por
    )

    messages.success(
        request,
        'Solicitação recusada com sucesso.'
    )

    return redirect(
        'estoque:caixa_solicitacoes'
    )

@login_required
def minhas_solicitacoes(request):

    solicitacoes = (
        Solicitacao.objects
        .filter(criado_por=request.user)
        .order_by('-criado_em')
    )

    return render(
        request,
        'estoque/solicitacoes/minhas.html',
        {
            'solicitacoes': solicitacoes
        }
    )

@login_required
@require_POST
def solicitar_transferencia_lote(request):
    data = json.loads(request.body)

    ids = data.get('equipamentos', [])
    destino = request.user.perfil.regionais.first()  # ou regra

    for eid in ids:
        equipamento = Equipamento.objects.get(id=eid)

        Solicitacao.objects.create(
            produto=equipamento.produto,
            quantidade=1,
            regional_solicitante=destino,
            criado_por=request.user
        )

@login_required
@role_required('gestor', 'operador', 'admin')
def receber_transferencia(request, transferencia_id):

    transferencia = get_object_or_404(
        Transferencia.objects.select_related(
            'regional_origem',
            'regional_destino',
            'solicitado_por'
        ).prefetch_related(
            'itens__equipamento__produto'
        ),
        id=transferencia_id
    )

    perfil = request.user.perfil

    if (
        perfil.role != 'admin'
        and not perfil.regionais.filter(
            id=transferencia.regional_destino_id
        ).exists()
    ):
        messages.error(request, 'Sem permissão para receber esta transferência.')
        return redirect('estoque:caixa_transferencias')

    if transferencia.status != 'EM_TRANSITO':
        messages.error(request, 'Transferência não está em trânsito.')
        return redirect('estoque:caixa_transferencias')

    itens = transferencia.itens.select_related(
        'equipamento',
        'equipamento__produto'
    )

    if request.method == 'POST':

        total_recebidos = 0
        total_divergentes = 0
        total_nao_recebidos = 0

        divergencia_detectada = False
        pendencia_detectada = False

        usuarios = None
        comunicado = None

        try:

            with transaction.atomic():

                for item in itens:

                    equipamento = item.equipamento

                    status_item = request.POST.get(
                        f'status_item_{item.id}',
                        'RECEBIDO'
                    )

                    if status_item == 'RECEBIDO':

                        equipamento.regional = transferencia.regional_destino
                        equipamento.status = 'ATIVO'
                        equipamento.save(update_fields=['regional', 'status'])

                        item.status = 'RECEBIDO'
                        item.save(update_fields=['status'])

                        Historico.objects.create(
                            equipamento=equipamento,
                            tipo_acao='TRANSFERENCIA_RECEBIDA',
                            usuario=request.user,
                            detalhes={
                                'transferencia_id': transferencia.id,
                                'protocolo': transferencia.protocolo,
                            }
                        )

                        total_recebidos += 1

                    elif status_item == 'DIVERGENTE':

                        serie_recebida = request.POST.get(f'serie_recebida_{item.id}', '')
                        patrimonio_recebido = request.POST.get(f'patrimonio_recebido_{item.id}', '')
                        observacao = request.POST.get(f'observacao_item_{item.id}', '')

                        equipamento.regional = transferencia.regional_destino
                        equipamento.status = 'ATIVO'
                        equipamento.save(update_fields=['regional', 'status'])

                        item.status = 'DIVERGENTE'
                        item.serie_recebida = serie_recebida
                        item.patrimonio_recebido = patrimonio_recebido
                        item.observacao_recebimento = observacao
                        item.save()

                        DivergenciaTransferencia.objects.create(
                            transferencia=transferencia,
                            item=item,
                            equipamento_enviado=equipamento,
                            serie_recebida=serie_recebida,
                            patrimonio_recebido=patrimonio_recebido
                        )

                        Historico.objects.create(
                            equipamento=equipamento,
                            tipo_acao='TRANSFERENCIA_DIVERGENTE',
                            usuario=request.user,
                            detalhes={
                                'transferencia_id': transferencia.id,
                                'protocolo': transferencia.protocolo,
                                'serie_recebida': serie_recebida,
                                'patrimonio_recebido': patrimonio_recebido,
                                'observacao': observacao,
                            }
                        )

                        divergencia_detectada = True
                        total_divergentes += 1

                    elif status_item == 'NAO_RECEBIDO':

                        equipamento.regional = transferencia.regional_origem
                        equipamento.status = 'ATIVO'
                        equipamento.save(update_fields=['regional', 'status'])

                        item.status = 'NAO_RECEBIDO'
                        item.save(update_fields=['status'])

                        PendenciaTransferencia.objects.create(
                            transferencia=transferencia,
                            item=item,
                            equipamento=equipamento,
                            motivo='NAO_RECEBIDO'
                        )

                        Historico.objects.create(
                            equipamento=equipamento,
                            tipo_acao='ITEM_NAO_RECEBIDO',
                            usuario=request.user,
                            detalhes={
                                'transferencia_id': transferencia.id,
                                'protocolo': transferencia.protocolo,
                            }
                        )

                        pendencia_detectada = True
                        total_nao_recebidos += 1

                transferencia.status = 'CONCLUIDA'
                transferencia.data_recebimento = timezone.now()
                transferencia.save(update_fields=['status', 'data_recebimento'])

                usuarios = (
                    User.objects.filter(perfil__regionais=transferencia.regional_origem)
                    | User.objects.filter(perfil__role='admin')
                ).distinct()

        except Exception as e:
            messages.error(request, f'Erro ao receber transferência: {e}')
            return redirect('estoque:receber_transferencia', transferencia.id)

        try:

            if divergencia_detectada and pendencia_detectada:
                titulo = f'Transferência {transferencia.protocolo} com divergências e pendências'
            elif divergencia_detectada:
                titulo = f'Transferência {transferencia.protocolo} com divergências'
            elif pendencia_detectada:
                titulo = f'Transferência {transferencia.protocolo} com pendências'
            else:
                titulo = f'Transferência {transferencia.protocolo} concluída sem ocorrências'

            itens_detalhados = []

            for item in itens:

                if item.status not in ['DIVERGENTE', 'NAO_RECEBIDO']:
                    continue

                eq = item.equipamento

                itens_detalhados.append({
                    "produto": eq.produto.descricao if eq.produto else "",
                    "serie_enviada": getattr(eq, "serie", ""),
                    "patrimonio_enviado": getattr(eq, "patrimonio", ""),
                    "status": item.status,
                    "serie_recebida": getattr(item, "serie_recebida", ""),
                    "patrimonio_recebido": getattr(item, "patrimonio_recebido", ""),
                    "observacao": getattr(item, "observacao_recebimento", ""),
                })

            conteudo = (
                f"Transferência: {transferencia.protocolo}\n\n"
                f"Origem: {transferencia.regional_origem.nome}\n"
                f"Destino: {transferencia.regional_destino.nome}\n\n"
                f"Detalhamento por item:\n"
            )

            for i, item in enumerate(itens_detalhados, start=1):
                conteudo += (
                    f"\nItem {i}:\n"
                    f"Produto: {item['produto']}\n"
                    f"Status: {item['status']}\n"
                    f"Enviado Série: {item['serie_enviada']} | Patrimônio: {item['patrimonio_enviado']}\n"
                    f"Recebido Série: {item['serie_recebida']} | Patrimônio: {item['patrimonio_recebido']}\n"
                    f"Observação: {item['observacao']}\n"
                    "-----------------------------"
                )

            comunicado = Comunicado.objects.create(
                titulo=titulo,
                mensagem=conteudo,
                tipo='OPERACIONAL',
                criado_por=request.user,
                ativo=True
            )

            comunicado.usuarios.add(*usuarios)

        except Exception:
            pass

        messages.success(
            request,
            (
                f'Concluído. Recebidos: {total_recebidos} | '
                f'Divergentes: {total_divergentes} | '
                f'Pendentes: {total_nao_recebidos}'
            )
        )

        return redirect('estoque:caixa_transferencias')

    return render(
        request,
        'estoque/receber_transferencia.html',
        {
            'transferencia': transferencia,
            'itens': itens
        }
    )

@login_required
@role_required('gestor','admin')
def cancelar_transferencia(request, transferencia_id):
    transferencia = get_object_or_404(
        secure_queryset(
            Transferencia.objects.select_related('equipamento'),
            request.user,
            'equipamento__regional__empresa'
        ),
        id=transferencia_id
    )

    if transferencia.status != 'PENDENTE':
        messages.error(request, "Apenas pendentes.")
        return redirect('estoque:lista_transferencias')

    with transaction.atomic():

        transferencia = Transferencia.objects.select_for_update().get(id=transferencia.id)

        transferencia.status = 'CANCELADO'
        transferencia.save(update_fields=['status'])

        equipamento = transferencia.equipamento
        equipamento.status = 'ATIVO'
        equipamento.save(update_fields=['status'])

        Historico.objects.create(
            equipamento=equipamento,
            tipo_acao='TRANSFERENCIA_CANCELADA',
            usuario=request.user,
            detalhes={
                'origem': transferencia.regional_origem.nome,
                'destino': transferencia.regional_destino.nome,
                'protocolo': transferencia.protocolo
            }
        )

    messages.success(request, "Cancelada com sucesso.")
    return redirect('estoque:lista_transferencias')

@login_required
@role_required('admin', 'gestor')
def lista_transferencias(request):

    perfil = request.user.perfil

    base_qs = (
        Transferencia.objects
        .select_related(
            'regional_origem',
            'regional_destino',
            'solicitado_por',
        )
        .prefetch_related(
            'itens',
            'itens__equipamento',
            'itens__equipamento__produto'
        )
        .order_by('-data_envio')
    )

    if perfil.role != 'admin':
        base_qs = base_qs.filter(
            Q(regional_destino__in=perfil.regionais_ids) |
            Q(regional_origem=perfil.regionais.first())
        )

    transferencias = list(base_qs)

    hoje = timezone.now().date()

    total_pendentes = sum(t.status == 'PENDENTE' for t in transferencias)
    total_em_transito = sum(t.status == 'EM_TRANSITO' for t in transferencias)
    total_concluidas = sum(t.status in ['CONCLUIDA', 'RECEBIDO'] for t in transferencias)
    total_canceladas = sum(t.status == 'CANCELADO' for t in transferencias)

    for t in transferencias:
        t.pode_receber = (
            t.status == 'PENDENTE'
            and (
                perfil.role == 'admin'
                or t.regional_destino.id in perfil.regionais_ids
            )
        )

        data_envio = t.data_envio.date() if t.data_envio else hoje
        base = t.data_recebimento.date() if t.data_recebimento else hoje
        t.dias = (base - data_envio).days

    return render(request, 'estoque/transferencia/listar.html', {
        'transferencias': transferencias,
        'total_pendentes': total_pendentes,
        'total_em_transito': total_em_transito,
        'total_concluidas': total_concluidas,
        'total_canceladas': total_canceladas,
    })

@login_required
@role_required('admin', 'gestor')
def equipamentos_por_regional(request, produto_id, regional_id):
    perfil = request.user.perfil

    if not perfil.is_admin and not perfil.regionais.filter(id=regional_id).exists():
        return JsonResponse({'erro': 'Acesso negado a esta regional'}, status=403)

    equipamentos = Equipamento.objects.filter(
        produto_id=produto_id,
        regional_id=regional_id
    )

    data = {
        'equipamentos': [
            {
                'id': e.id,
                'numero_serie': e.numero_serie,
                'patrimonio': e.patrimonio,
                'status': e.status,
                'foto': e.foto.url if e.foto else None
            }
            for e in equipamentos
        ],
        'regionais': list(
            Base.objects.exclude(id=regional_id).values('id', 'nome')
        )
    }
    return JsonResponse(data)

@login_required
@role_required('admin', 'gestor')
def editar_equipamento(request, equipamento_id):

    equipamento = get_object_or_404(
        Equipamento.objects.select_related(
            'produto',
            'regional'
        ),
        id=equipamento_id
    )

    perfil = request.user.perfil

    is_admin = perfil.is_admin
    is_gestor = perfil.is_gestor

    bases = (
        Base.objects.all().order_by('nome')
        if is_admin else []
    )

    produtos = (
        Produto.objects.all()
        .order_by(
            'categoria',
            'descricao'
        )
    )

    historico = (
        Historico.objects
        .filter(equipamento=equipamento)
        .select_related(
            'usuario',
            'equipamento'
        )
        .order_by('-data')
        .first()
    )

    if request.method == 'GET':

        return render(
            request,
            'estoque/editar_equipamento.html',
            {
                'equipamento': equipamento,
                'historico': historico,
                'bases': bases,
                'produtos': produtos,
                'status_choices': Equipamento.STATUS_CHOICES,
                'is_admin': is_admin,
                'is_gestor': is_gestor,
            }
        )

    senha_confirmacao = request.POST.get(
        'senha_confirmacao',
        ''
    )

    if not request.user.check_password(
        senha_confirmacao
    ):
        messages.error(
            request,
            'Senha inválida.'
        )

        return redirect(
            request.META.get(
                'HTTP_REFERER',
                '/'
            )
        )

    patrimonio = request.POST.get(
        'patrimonio',
        ''
    ).strip()

    numero_serie = request.POST.get(
        'numero_serie',
        ''
    ).strip()

    observacao = request.POST.get(
        'observacao_edicao',
        ''
    ).strip()

    foto = request.FILES.get('foto')

    produto_id = request.POST.get(
        'produto'
    )

    regional_id = request.POST.get(
        'regional'
    )

    responsavel = request.POST.get(
        'responsavel',
        ''
    ).strip()

    status = request.POST.get(
        'status',
        ''
    ).strip()

    try:

        with transaction.atomic():

            snapshot_antes = {
                'produto_id': equipamento.produto_id,
                'produto': (
                    equipamento.produto.descricao
                    if equipamento.produto else None
                ),
                'patrimonio': equipamento.patrimonio,
                'numero_serie': equipamento.numero_serie,
                'regional_id': equipamento.regional_id,
                'regional': (
                    equipamento.regional.nome
                    if equipamento.regional else None
                ),
                'responsavel': equipamento.responsavel,
                'status': equipamento.status,
                'foto': (
                    str(equipamento.foto)
                    if equipamento.foto else None
                ),
            }

            alteracoes = {}

            if patrimonio != equipamento.patrimonio:

                alteracoes['patrimonio'] = {
                    'antes': equipamento.patrimonio,
                    'depois': patrimonio,
                }

                equipamento.patrimonio = patrimonio

            if numero_serie != equipamento.numero_serie:

                alteracoes['numero_serie'] = {
                    'antes': equipamento.numero_serie,
                    'depois': numero_serie,
                }

                equipamento.numero_serie = numero_serie

            if foto:

                alteracoes['foto'] = {
                    'antes': (
                        str(equipamento.foto)
                        if equipamento.foto else None
                    ),
                    'depois': foto.name,
                }

                equipamento.foto = foto

            if is_admin:

                if produto_id:

                    novo_produto = get_object_or_404(
                        Produto,
                        id=produto_id
                    )

                    if (
                        equipamento.produto_id
                        != novo_produto.id
                    ):

                        alteracoes['produto'] = {
                            'antes': (
                                equipamento.produto.descricao
                                if equipamento.produto else None
                            ),
                            'depois': novo_produto.descricao,
                        }

                        equipamento.produto = novo_produto

                if regional_id:

                    nova_regional = get_object_or_404(
                        Base,
                        id=regional_id
                    )

                    if (
                        equipamento.regional_id
                        != nova_regional.id
                    ):

                        alteracoes['regional'] = {
                            'antes': (
                                equipamento.regional.nome
                                if equipamento.regional else None
                            ),
                            'depois': nova_regional.nome,
                        }

                        equipamento.regional = nova_regional

                if responsavel != equipamento.responsavel:

                    alteracoes['responsavel'] = {
                        'antes': equipamento.responsavel,
                        'depois': responsavel,
                    }

                    equipamento.responsavel = responsavel

                if (
                    status
                    and
                    status != equipamento.status
                ):

                    alteracoes['status'] = {
                        'antes': equipamento.status,
                        'depois': status,
                    }

                    equipamento.status = status

            if not alteracoes:

                messages.warning(
                    request,
                    'Nenhuma alteração foi realizada.'
                )

                return redirect(
                    request.META.get(
                        'HTTP_REFERER',
                        '/'
                    )
                )

            equipamento.save()

            Historico.objects.create(
                equipamento=equipamento,
                usuario=request.user,
                tipo_acao='EDICAO',
                detalhes={
                    'observacao': observacao,
                    'alteracoes': alteracoes,
                    'snapshot_antes': snapshot_antes,
                    'snapshot_depois': {
                        'produto_id': equipamento.produto_id,
                        'produto': (
                            equipamento.produto.descricao
                            if equipamento.produto else None
                        ),
                        'patrimonio': equipamento.patrimonio,
                        'numero_serie': equipamento.numero_serie,
                        'regional_id': equipamento.regional_id,
                        'regional': (
                            equipamento.regional.nome
                            if equipamento.regional else None
                        ),
                        'responsavel': equipamento.responsavel,
                        'status': equipamento.status,
                        'foto': (
                            str(equipamento.foto)
                            if equipamento.foto else None
                        ),
                    }
                }
            )

        messages.success(
            request,
            'Equipamento atualizado com sucesso.'
        )

    except IntegrityError:

        messages.error(
            request,
            'Não foi possível salvar o equipamento. '
            'Já existe outro equipamento utilizando '
            'o mesmo patrimônio ou número de série.'
        )

    except Exception as e:

        messages.error(
            request,
            f'Erro ao atualizar equipamento: {str(e)}'
        )

    return redirect(
        request.META.get(
            'HTTP_REFERER',
            '/'
        )
    )

@login_required
def checklist_view(request):
    # --- POST: Criar checklist ---
    if request.method == 'POST':
        try:
            inventario_id = request.POST.get('inventario')
            if not inventario_id:
                messages.error(request, 'É necessário selecionar um inventário.')
                return redirect('estoque:checklist')

            inventario = get_object_or_404(
                Inventario.objects.select_related('base', 'cliente'),
                id=inventario_id
            )

            # Verifica permissão de acesso à base
            if not request.user.perfil.is_admin:
                regionais_ids = request.user.perfil.regionais_ids
                if inventario.base_id not in regionais_ids:
                    messages.error(request, 'Você não tem acesso à base deste inventário.')
                    return redirect('estoque:checklist')

            # Captura equipamentos selecionados
            categorias_equipamentos = ['router', 'coletor', 'notebook', 'impressora']
            equipamentos_ids = []
            for categoria in categorias_equipamentos:
                equipamentos_ids.extend(request.POST.getlist(f'equipamentos_{categoria}'))

            # Captura insumos enviados pela tabela carregada via JavaScript.
            insumos_payload = []
            for key, quantidade in request.POST.items():
                match = re.match(r'^insumo_(\d+)_enviada$', key)
                if match and quantidade and float(quantidade) > 0:
                    insumos_payload.append((match.group(1), quantidade))

            # Captura lotes de TAG. Cada lote guarda o ponto inicial no envio;
            # o ponto final utilizado será informado no retorno do checklist.
            tags_payload = []
            for rolo_id in request.POST.getlist('rolo_tag_ids'):
                numero_inicial = request.POST.get(f'tag_inicial_rolo_{rolo_id}')
                if numero_inicial:
                    tags_payload.append((rolo_id, numero_inicial))

            if not equipamentos_ids and not insumos_payload and not tags_payload:
                messages.error(request, 'Selecione ao menos um equipamento, informe um insumo ou adicione um lote de TAG.')
                return redirect('estoque:checklist')

            with transaction.atomic():
                checklist = ChecklistService.criar(
                    inventario=inventario,
                    usuario=request.user,
                    observacao=request.POST.get('observacao', '')
                )

                if equipamentos_ids:
                    equipamentos = Equipamento.objects.select_related('regional', 'produto').filter(id__in=equipamentos_ids)
                    for equipamento in equipamentos:
                        ChecklistService.adicionar_equipamento(
                            checklist=checklist,
                            equipamento=equipamento,
                            usuario=request.user
                        )

                if insumos_payload:
                    insumos_ids = [item[0] for item in insumos_payload]
                    insumos_dict = {str(insumo.id): insumo for insumo in Insumo.objects.filter(id__in=insumos_ids)}
                    for insumo_id, quantidade in insumos_payload:
                        insumo = insumos_dict.get(insumo_id)
                        if insumo:
                            ChecklistService.registrar_envio_item(
                                checklist=checklist,
                                insumo=insumo,
                                quantidade_enviada=quantidade,
                                usuario=request.user
                            )

                if tags_payload:
                    rolos_ids = [item[0] for item in tags_payload]
                    rolos_dict = {
                        str(rolo.id): rolo
                        for rolo in RoloTag.objects.select_related('lote').filter(id__in=rolos_ids)
                    }
                    for rolo_id, numero_inicial in tags_payload:
                        rolo = rolos_dict.get(rolo_id)
                        if rolo:
                            ChecklistService.adicionar_lote_tag(
                                checklist=checklist,
                                lote=rolo.lote,
                                rolo=rolo,
                                numero_inicial_utilizado=numero_inicial,
                                usuario=request.user
                            )

                checklist.status = 'EM_EXECUCAO'
                checklist.save(update_fields=['status'])

                if inventario.status == 'PLANEJADO':
                    inventario.status = 'EM_ANDAMENTO'
                    inventario.save(update_fields=['status'])

            messages.success(request, 'Checklist criado e estoque movimentado com sucesso!')
            return redirect('estoque:checklist')

        except Exception as e:
            messages.error(request, f'Erro ao criar checklist: {str(e)}')
            return redirect('estoque:checklist')

    # --- GET: Exibir formulário ---
    regionais_ids = request.user.perfil.regionais_ids

    if request.user.perfil.is_admin:
        equipamentos = Equipamento.objects.filter(status='ATIVO')
        inventarios = Inventario.objects.filter(
            status='PLANEJADO',
            data_inicio=date.today()
        )
        lotes_tags = RoloTag.objects.filter(status='DISPONIVEL', lote__ativo=True).select_related('lote', 'lote__base')
    else:
        equipamentos = Equipamento.objects.filter(
            status='ATIVO',
            regional_id__in=regionais_ids
        )
        inventarios = Inventario.objects.filter(
            status='PLANEJADO',
            base__in=request.user.perfil.regionais.all(),
            data_inicio=date.today()
        )
        lotes_tags = RoloTag.objects.filter(
            status='DISPONIVEL',
            lote__ativo=True,
            lote__base_id__in=regionais_ids
        ).select_related('lote', 'lote__base')

    # ----- LISTA DE ITENS FIXOS DO CHECKLIST -----
    ITENS_CHECKLIST = [
        # DEPARTAMENTO PESSOAL (itens 1 a 26)
        {"id": 1, "descricao": "Toner Impressora Laser", "grupo": "DEPARTAMENTO PESSOAL"},
        {"id": 2, "descricao": "Marcador de Coleta - AZUL ESCURO", "grupo": "DEPARTAMENTO PESSOAL"},
        {"id": 3, "descricao": "Marcador de Coleta - AZUL CLARO", "grupo": "DEPARTAMENTO PESSOAL"},
        {"id": 4, "descricao": "Touca", "grupo": "DEPARTAMENTO PESSOAL"},
        {"id": 5, "descricao": "Luva", "grupo": "DEPARTAMENTO PESSOAL"},
        {"id": 6, "descricao": "Máscara", "grupo": "DEPARTAMENTO PESSOAL"},
        {"id": 7, "descricao": "Grampeador", "grupo": "DEPARTAMENTO PESSOAL"},
        {"id": 8, "descricao": "Durex", "grupo": "DEPARTAMENTO PESSOAL"},
        {"id": 9, "descricao": "Papel Sulfite (Pacote)", "grupo": "DEPARTAMENTO PESSOAL"},
        {"id": 10, "descricao": "Etiqueta Setor 0001", "grupo": "DEPARTAMENTO PESSOAL", "tag": True},
        {"id": 11, "descricao": "Etiqueta Setor 1000", "grupo": "DEPARTAMENTO PESSOAL", "tag": True},
        {"id": 12, "descricao": "Etiqueta Setor 2000", "grupo": "DEPARTAMENTO PESSOAL", "tag": True},
        {"id": 13, "descricao": "Etiqueta Setor 3000", "grupo": "DEPARTAMENTO PESSOAL", "tag": True},
        {"id": 14, "descricao": "Etiqueta Setor 3500 - Peso Variável", "grupo": "DEPARTAMENTO PESSOAL", "tag": True},
        {"id": 15, "descricao": "Etiqueta Setor 4000", "grupo": "DEPARTAMENTO PESSOAL", "tag": True},
        {"id": 16, "descricao": "Etiqueta Setor 5000", "grupo": "DEPARTAMENTO PESSOAL", "tag": True},
        {"id": 17, "descricao": "Etiqueta Setor 6000", "grupo": "DEPARTAMENTO PESSOAL", "tag": True},
        {"id": 18, "descricao": "Etiqueta Setor 7000", "grupo": "DEPARTAMENTO PESSOAL", "tag": True},
        {"id": 19, "descricao": "Etiqueta Setor 8000", "grupo": "DEPARTAMENTO PESSOAL", "tag": True},
        {"id": 20, "descricao": "Etiqueta Setor 9000", "grupo": "DEPARTAMENTO PESSOAL", "tag": True},
        {"id": 21, "descricao": "Marcador Coletado", "grupo": "DEPARTAMENTO PESSOAL"},
        {"id": 22, "descricao": "Calça Térmica", "grupo": "DEPARTAMENTO PESSOAL"},
        {"id": 23, "descricao": "Capa Térmica", "grupo": "DEPARTAMENTO PESSOAL"},
        {"id": 24, "descricao": "Capacete", "grupo": "DEPARTAMENTO PESSOAL"},
        {"id": 25, "descricao": "Botas do 33/48", "grupo": "DEPARTAMENTO PESSOAL"},
        {"id": 26, "descricao": "Cinto de segurança", "grupo": "DEPARTAMENTO PESSOAL"},
        # FIOS E CABOS (itens 27 a 40)
        {"id": 27, "descricao": "Access Point + Fonte", "grupo": "FIOS E CABOS"},
        {"id": 28, "descricao": "Router Hap + Fonte", "grupo": "FIOS E CABOS", "equipamento": True},
        {"id": 29, "descricao": "Switch Poe Pro", "grupo": "FIOS E CABOS"},
        {"id": 30, "descricao": "Cabo Power", "grupo": "FIOS E CABOS"},
        {"id": 31, "descricao": "Cabo USB (Impressora)", "grupo": "FIOS E CABOS"},
        {"id": 32, "descricao": "Filtro de Linha", "grupo": "FIOS E CABOS"},
        {"id": 33, "descricao": "Transformador", "grupo": "FIOS E CABOS"},
        {"id": 34, "descricao": "Cabo Transformador", "grupo": "FIOS E CABOS"},
        {"id": 35, "descricao": "Teste Voltagem", "grupo": "FIOS E CABOS"},
        {"id": 36, "descricao": "Adaptador", "grupo": "FIOS E CABOS"},
        {"id": 37, "descricao": "Extensão", "grupo": "FIOS E CABOS"},
        {"id": 38, "descricao": "Cabo de Rede (RJ45)", "grupo": "FIOS E CABOS"},
        {"id": 39, "descricao": "Extensor de Rede / Carrinho", "grupo": "FIOS E CABOS"},
        {"id": 40, "descricao": "Cintos Coletor", "grupo": "FIOS E CABOS"},
        # COLETOR DE DADOS (itens 41 a 56)
        {"id": 41, "descricao": "Coletor de Dados", "grupo": "COLETOR DE DADOS", "equipamento": True},
        {"id": 42, "descricao": "Carregador de Bateria", "grupo": "COLETOR DE DADOS"},
        {"id": 43, "descricao": "Fonte Carregador de Bateria", "grupo": "COLETOR DE DADOS"},
        {"id": 44, "descricao": "Bateria Coletor", "grupo": "COLETOR DE DADOS"},
        {"id": 45, "descricao": "Carregador Tipo C (Coletor Android)", "grupo": "COLETOR DE DADOS"},
        {"id": 46, "descricao": "Cabo USB (Berço)", "grupo": "COLETOR DE DADOS"},
        {"id": 47, "descricao": "Berço + Cabo USB", "grupo": "COLETOR DE DADOS"},
        {"id": 48, "descricao": "Mouse", "grupo": "COLETOR DE DADOS"},
        {"id": 49, "descricao": "Placa 3G", "grupo": "COLETOR DE DADOS"},
        {"id": 50, "descricao": "Tablet", "grupo": "COLETOR DE DADOS"},
        {"id": 51, "descricao": "Notebook", "grupo": "COLETOR DE DADOS", "equipamento": True},
        {"id": 52, "descricao": "Fonte Notebook", "grupo": "COLETOR DE DADOS"},
        {"id": 53, "descricao": "Impressora Laser", "grupo": "COLETOR DE DADOS", "equipamento": True},
        {"id": 54, "descricao": "Escada", "grupo": "COLETOR DE DADOS"},
        {"id": 55, "descricao": "Balança", "grupo": "COLETOR DE DADOS"},
        {"id": 56, "descricao": "Fonte Balança", "grupo": "COLETOR DE DADOS"},
    ]

    context = {
        'coletores': equipamentos.filter(produto__categoria='Coletores'),
        'impressoras': equipamentos.filter(produto__categoria='Impressoras'),
        'notebooks': equipamentos.filter(produto__categoria='Notebooks'),
        'routers': equipamentos.filter(produto__categoria='Routers'),
        'inventarios': inventarios,
        'insumos': [],  # será preenchido via JavaScript
        'lotes_tags': lotes_tags,
        'itens_checklist': ITENS_CHECKLIST,  # <--- ADICIONADO
        'url_name': 'checklist',
    }
    return render(request, 'estoque/checklist.html', context)

def get_equipamentos_disponiveis(request):
    regional_id = request.GET.get('regional')
    categoria = request.GET.get('categoria')

    if not regional_id or not categoria:
        return JsonResponse({'results': []})

    equipamentos = Equipamento.objects.filter(status='ATIVO', regional_id=regional_id, produto__categoria=categoria).select_related('produto')

    data = [{
        'id': eq.id,
        'text': f"{eq.numero_serie} - {eq.produto.descricao} ({eq.patrimonio})",
        'numero_serie': eq.numero_serie,
        'patrimonio': eq.patrimonio,
        'produto_descricao': eq.produto.descricao
    } for eq in equipamentos]

    return JsonResponse({'results': data})

def get_lotes_tags_disponiveis(request):
    regional_id = request.GET.get('regional')

    if not regional_id:
        return JsonResponse({'results': []})

    if not request.user.perfil.is_admin:
        regionais_ids = request.user.perfil.regionais_ids
        if int(regional_id) not in regionais_ids:
            return JsonResponse({'results': []}, status=403)

    lotes = LoteTag.objects.filter(ativo=True, quantidade_disponivel__gt=0, base_id=regional_id)

    data = [{
        'id': lote.id,
        'text': f"Lote {lote.numero_inicial} a {lote.numero_final} (disp: {lote.quantidade_disponivel})",
        'numero_inicial': lote.numero_inicial,
        'numero_final': lote.numero_final,
        'quantidade_disponivel': lote.quantidade_disponivel
    } for lote in lotes]

    return JsonResponse({'results': data})

