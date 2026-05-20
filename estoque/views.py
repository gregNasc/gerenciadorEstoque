from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors
from openpyxl import Workbook
from django.db import transaction
from .forms import EquipamentoForm
from django.http import HttpResponse
from .models import (Produto, Equipamento, Transferencia, Sick, Historico, Base, Perfil, Empresa, Solicitacao, SolicitacaoItem, AlocacaoSolicitacaoItem, TransferenciaItem, StatusEquipamento) #Regional
from .models import (Comunicado, ComunicadoArquivo, ComunicadoLeitura, ComunicadoOculto, MensagemDestino, MensagemArquivo, Empresa, Notificacao)
from .utils import filtrar_por_empresa, qs_equipamentos, qs_historico, qs_bases
from django.db.models import Count, Q, F
from django.utils.dateparse import parse_date
from django.utils import timezone
from datetime import datetime, time
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from .decorators import role_required
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .utils import EstoqueService
from .security import secure_queryset
#from estoque.services.transferencia_services import gerar_transferencias_da_solicitacao
import json
import re
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
            .values('produto__id', 'produto__descricao')
            .annotate(
                total=Count('id'),
                ativos=Count('id', filter=Q(status='ATIVO')),
                sick=Count('id', filter=Q(status='SICK')),
                transferencia=Count('id', filter=Q(status='TRANSFERENCIA')),
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
                transferencia=Count('id', filter=Q(status='TRANSFERENCIA')),
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

        regional_data = {
            'regional__id': regional.id,
            'regional__nome': regional.nome,
            'total': total,
            'ativos': ativos,
            'sick': sick,
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
            transferencia=Count('id', filter=Q(status='TRANSFERENCIA')),
            manutencao=Count('id', filter=Q(status='MANUTENCAO')),
        )
        .order_by('produto__categoria', 'produto__descricao')
    )

    categorias_dict = defaultdict(list)

    for produto in produtos_agrupados:
        categorias_dict[produto['produto__categoria']].append({
            'id': produto['produto__id'],
            'nome': produto['produto__descricao'],
            'total': produto['total'],
            'ativos': produto['ativos'],
            'sick': produto['sick'],
            'transferencia': produto['transferencia'],
            'manutencao': produto['manutencao'],
        })

    produtos_detalhados = [
        {
            'categoria': categoria,
            'produtos': produtos
        }
        for categoria, produtos in categorias_dict.items()
    ]

    kpis_regional = EstoqueService.get_kpis_gerais(equipamentos)
    disponibilidade = EstoqueService.get_disponibilidade(equipamentos)

    regional = Base.objects.only('id', 'nome').get(id=regional_id)

    return JsonResponse({
        'categorias': produtos_detalhados,
        'regional_id': regional.id,
        'regional_nome': regional.nome,
        'total_regional': kpis_regional['total'],
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
        Equipamento.objects.select_related('regional', 'produto'),
        request.user
    )

    regional_id = request.GET.get('regional')

    if regional_id and regional_id.isdigit():
        equipamentos = equipamentos.filter(regional_id=regional_id)

    produtos_agrupados = equipamentos.values(
        'produto__id',
        'produto__descricao',
    ).annotate(
        total=Count('id'),
        ativos=Count('id', filter=Q(status='ATIVO')),
        sick=Count('id', filter=Q(status='SICK')),
        transferencia=Count('id', filter=Q(status='EM_TRANSFERENCIA')),
        manutencao=Count('id', filter=Q(status='MANUTENCAO')),
    ).order_by('produto__descricao')

    if perfil.is_admin:
        regionais = Base.objects.all()
    else:
        regionais = perfil.regionais.all()

    return render(request, 'estoque/estoque.html', {
        'produtos_agrupados': produtos_agrupados,
        'regionais': regionais,
        'regional_selecionada': regional_id
    })


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
        .values('regional__id', 'regional__nome')
        .annotate(total=Count('id'))
        .order_by('regional__nome')
    )

    if regional_id:
        qs = qs.filter(regional_id=regional_id)

    equipamentos = [
        {
            "id": e.id,
            "numero_serie": e.numero_serie,
            "patrimonio": e.patrimonio,
            "status": e.status,
            "responsavel": e.responsavel,
            "foto": e.foto.url if e.foto else None
        }
        for e in qs
    ]

    transferencias = Transferencia.objects.filter(
        alocacao__item__solicitacao_id=solicitacao_id,
        status='PENDENTE'

    ).select_related('regional_origem', 'regional_destino')

    if not perfil.is_admin:
        transferencias = transferencias.filter(
            regional_origem__in=perfil.regionais_ids
        )

    if regional_id:
        transferencias = transferencias.filter(regional_origem_id=regional_id)

    trans_list = [
        {
            "descricao": f"A caminho para {t.regional_destino.nome}",
            "origem": t.regional_origem.nome,
            "destino": t.regional_destino.nome,
            "status": t.status,
        }
        for t in transferencias
    ]

    return JsonResponse({
        "regionais": list(dados_regionais),
        "equipamentos": list(equipamentos),
        "transferencias": trans_list,
        "regional_id": regional_id
    })

# ----------------- SICK -----------------
@login_required
@role_required('admin', 'gestor')
def sick_view(request):

    perfil = request.user.perfil

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
            if (
                    not perfil.is_admin and
                    sick.equipamento.regional_id not in perfil.regionais_ids
            ):
                messages.error(request, "Sem permissão.")
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

            if novo_status in ['ATIVO', 'INATIVO', 'SUCATA']:

                sick.data_resolucao = timezone.now()
                sick.ativo = False
                sick.resolvido_por = request.user

            elif novo_status == 'MANUTENCAO':

                sick.ativo = True
                sick.data_resolucao = None

            #elif novo_status == 'MANUTENCAO':

            #    sick.ativo = True
            #    sick.data_resolucao = None

            sick.status_final = novo_status

            sick.save()

            equipamento = sick.equipamento
            equipamento.status = novo_status

            equipamento.save(update_fields=['status'])

            Historico.objects.create(
                equipamento=equipamento,
                tipo_acao='SICK_RESOLVIDO',
                usuario=request.user,
                detalhes={
                    'sick_id': sick.id,
                    'status_final': novo_status,
                    'motivo_manutencao': motivo_manutencao,
                    'previsao_retorno': previsao_retorno,
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

    if perfil.is_admin:

        sicks = qs

    else:

        if not perfil.regionais.exists():

            sicks = qs.none()

        else:

            sicks = qs.filter(
                equipamento__regional=perfil.regionais
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

    if perfil.is_admin:
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

    if equipamento.status == 'SICK':
        return JsonResponse({'erro': 'Já está em SICK'}, status=400)

    with transaction.atomic():
        equipamento.status = 'SICK'
        equipamento.save(update_fields=['status'])

        Sick.objects.create(
            equipamento=equipamento,
            motivo='Via sistema',
            categoria='OPERACIONAL',
            #descricao=descricao
        )

        Historico.objects.create(
            equipamento=equipamento,
            tipo_acao='STATUS',
            usuario=request.user,
            detalhes={'novo_status': 'SICK'}
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
    ws.title = "Histórico de Equipamentos"

    headers = [
        'Data',
        'Regional',
        'Equipamento',
        'Número de Série',
        'Patrimônio',
        'Tipo de Ação',
        'Usuário',
        'Detalhes'
    ]
    ws.append(headers)

    historicos = Historico.objects.select_related(
        'equipamento',
        'equipamento__produto',
        'usuario',
        'equipamento__regional'
    ).order_by('-data')

    regional_nome = "TODAS"

    if regional_id:
        historicos = historicos.filter(equipamento__regional_id=regional_id)

        regional_nome = (
            historicos.first().equipamento.regional.nome
            if historicos.exists()
            else "SEM_DADOS"
        )

    for h in historicos:
        ws.append([
            h.data.strftime('%d/%m/%Y %H:%M'),
            getattr(h.equipamento.regional, "nome", "N/A"),
            h.equipamento.produto.descricao,
            h.equipamento.numero_serie,
            h.equipamento.patrimonio,
            h.get_tipo_acao_display(),
            h.usuario.username if h.usuario else "Sistema",
            str(h.detalhes)[:200],
        ])

    filename = f"historico_equipamentos_{regional_nome}.xlsx".replace(" ", "_")

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename={filename}'

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

    historico = Historico.objects.filter(
        equipamento_id=equipamento_id
    ).order_by('-data').first()
    print("DEBUG HISTÓRICO:", historico)
    if not historico:
        return HttpResponse("""
            <div class="alert alert-warning">
                Nenhum histórico encontrado para este equipamento.
            </div>
        """)

    return render(request, 'estoque/partials/historico_detalhes.html', {
        'historico': historico
    })

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

            destinatarios = destinatarios.distinct()

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

            comunicado.usuarios.set(
                usuarios.distinct()
            )

        elif regionais_ids:

            usuarios = User.objects.filter(
                perfil__regionais__id__in=regionais_ids,
                is_active=True
            )

            if empresa_id:

                usuarios = usuarios.filter(
                    perfil__empresa_id=empresa_id
                )

            comunicado.usuarios.set(
                usuarios.distinct()
            )

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
def detalhe_comunicado(request, comunicado_id):

    perfil = request.user.perfil

    comunicado = get_object_or_404(

        Comunicado.objects.filter(

            Q(enviar_para_todos=True) |
            Q(usuarios=request.user) |
            Q(empresa=perfil.empresa)

        ).distinct(),

        id=comunicado_id
    )

    ComunicadoLeitura.objects.get_or_create(
        comunicado=comunicado,
        usuario=request.user
    )

    return render(
        request,
        'estoque/comunicados/detalhe.html',
        {
            'comunicado': comunicado
        }
    )

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

# ----------------- TRANSFERÊNCIAS  -----------------
@login_required
@role_required('admin')
def painel_alocacao(request, solicitacao_id):

    solicitacao = get_object_or_404(
        Solicitacao.objects.prefetch_related('itens'),
        id=solicitacao_id
    )

    if solicitacao.status != 'PENDENTE':
        messages.error(request, 'Solicitação já processada.')
        return redirect('estoque:caixa_solicitacoes')

    itens = solicitacao.itens.all()

    if request.method == 'POST':

        alocacoes_criadas = 0

        with transaction.atomic():

            for item in itens:

                prefix = f'alocacao_{item.id}_'

                for key, value in request.POST.items():

                    if not key.startswith(prefix):
                        continue

                    if not value:
                        continue

                    quantidade = int(value)

                    if quantidade <= 0:
                        continue

                    partes = key.replace(prefix, '').split('_')

                    if len(partes) != 2:
                        continue

                    regional_id, produto_id = partes

                    regional = Base.objects.get(id=regional_id)

                    alocacao = AlocacaoSolicitacaoItem.objects.create(
                        item=item,
                        regional_origem=regional,
                        quantidade=quantidade
                    )

                    transferencia = Transferencia.objects.create(
                        alocacao=alocacao,
                        solicitado_por=request.user,
                        regional_origem=regional,
                        regional_destino=solicitacao.regional_solicitante,
                        status='PENDENTE'
                    )

                    usuarios = User.objects.filter(
                        perfil__regionais=regional
                    ).distinct()

                    for usuario in usuarios:

                        Notificacao.objects.get_or_create(
                            usuario=usuario,
                            transferencia=transferencia,
                            solicitacao=solicitacao,
                            tipo='SOLICITACAO',
                            evento='APROVADA',
                            defaults={
                                'mensagem': (
                                    f'Solicitação #{solicitacao.id} '
                                    f'aguardando separação.'
                                ),
                                'link': f'/transferencias/{transferencia.id}/'
                            }
                        )

                    alocacoes_criadas += 1

            if alocacoes_criadas == 0:
                messages.error(request, 'Nenhuma alocação informada.')
                return redirect(
                    'estoque:painel_alocacao',
                    solicitacao_id=solicitacao.id
                )

            solicitacao.status = 'EM_TRANSFERENCIA'
            solicitacao.aprovado_por = request.user
            solicitacao.data_aprovacao = timezone.now()
            solicitacao.save()

        messages.success(
            request,
            'Transferências criadas com sucesso.'
        )

        return redirect('estoque:caixa_solicitacoes')

    estoque = get_estoque_por_produto()

    for item in itens:

        regionais_agrupados = {}

        for produto_id, dados in estoque.items():

            if (
                dados.get('categoria')
                and item.categoria
                and dados['categoria'].strip().lower()
                == item.categoria.strip().lower()
            ):

                for reg in dados['regionais']:

                    rid = reg['regional_id']

                    if rid not in regionais_agrupados:

                        regionais_agrupados[rid] = {
                            'regional': reg['regional'],
                            'regional_id': rid,
                            'total': 0,
                            'produtos': []
                        }

                    regionais_agrupados[rid]['total'] += reg['total']

                    regionais_agrupados[rid]['produtos'].append({
                        'produto_id': produto_id,
                        'produto': dados['produto'],
                        'disponivel': reg['total']
                    })

        for reg in regionais_agrupados.values():

            reg['produtos'] = sorted(
                reg['produtos'],
                key=lambda x: x['disponivel'],
                reverse=True
            )

        item.regionais = sorted(
            regionais_agrupados.values(),
            key=lambda x: x['total'],
            reverse=True
        )

    return render(
        request,
        'estoque/alocacao/painel.html',
        {
            'solicitacao': solicitacao,
            'itens': itens
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
@role_required('admin', 'gestor')
def caixa_solicitacoes(request):

    perfil = request.user.perfil

    qs = Solicitacao.objects.select_related(
        'criado_por',
        'regional_solicitante',
        'regional_origem'
    ).filter(
    status__in=['PENDENTE']
    )

    if perfil.role == 'gestor':
        qs = qs.filter(
            Q(regional_solicitante__in=perfil.regionais.all()) |
            Q(regional_origem__in=perfil.regionais.all())
        )

    qs = qs.order_by('-criado_em')

    return render(request, 'estoque/solicitacoes/caixa.html', {
        'solicitacoes': qs,
        'notificacoes_nao_lidas': qs.count()
    })
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

@login_required
@role_required('admin', 'gestor')
def pode_transferir(equipamento):
    if equipamento.status == 'SICK':
        return False, 'SICK'

    if Transferencia.objects.filter(
        equipamento=equipamento,
        status__in=['SOLICITADO', 'PENDENTE', 'ENVIADO']
    ).exists():
        return False, 'PENDENTE'

    return True, None

@login_required
@role_required('admin', 'gestor')
def criar_solicitacao(request):
    #print("USER:", request.user)
    #print("ROLE:", request.user.perfil.role)
    if request.method == 'POST':

        motivo = request.POST.get('motivo')
        categorias = request.POST.getlist('categoria')
        quantidades = request.POST.getlist('quantidade')

        if not motivo:
            messages.error(request, 'Informe o motivo da solicitação.')
            return redirect('estoque:criar_solicitacao')

        if not categorias:
            messages.error(request, 'Adicione pelo menos um item.')
            return redirect('estoque:criar_solicitacao')

        try:
            with transaction.atomic():

                solicitacao = Solicitacao.objects.create(
                    motivo=motivo,
                    regional_solicitante=request.user.perfil.regionais.first(),
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
                    raise ValueError('Nenhum item válido informado.')

        except Exception as e:
            messages.error(request, f'Erro ao criar solicitação: {str(e)}')
            return redirect('estoque:criar_solicitacao')

        messages.success(request, 'Solicitação criada com sucesso!')
        return redirect('estoque:caixa_solicitacoes')

    return render(request, 'estoque/solicitacoes/criar.html')

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
        Transferencia.objects.select_related(
            'regional_origem',
            'regional_destino',
            'solicitado_por',
            'alocacao',
            'alocacao__item'
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

    if not transferencia.alocacao or not transferencia.alocacao.item:
        messages.error(request, 'Transferência inválida: sem alocação.')
        return redirect('estoque:caixa_separacao')

    alocacao = transferencia.alocacao
    item = alocacao.item

    categoria = item.categoria
    quantidade = alocacao.quantidade

    equipamentos_disponiveis = Equipamento.objects.filter(
        regional=transferencia.regional_origem,
        status='ATIVO',
        produto__categoria=categoria
    ).select_related('produto')

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

    itens = transferencia.itens.select_related(
        'equipamento',
        'equipamento__produto'
    )

    return render(request, 'estoque/transferencia/detalhe.html', {
        'transferencia': transferencia,
        'itens': itens,
        'equipamentos_disponiveis': equipamentos_disponiveis,
        'quantidade_necessaria': quantidade,
        'categoria': categoria
    })

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
            id=transferencia.regional_destino.id
        ).exists()
    ):
        messages.error(
            request,
            'Sem permissão para receber esta transferência.'
        )
        return redirect('estoque:caixa_transferencias')

    if transferencia.status != 'EM_TRANSITO':
        messages.error(
            request,
            'Transferência não está em trânsito.'
        )
        return redirect('estoque:caixa_transferencias')

    itens = transferencia.itens.all()

    if request.method == 'POST':

        with transaction.atomic():

            for item in itens:

                equipamento = item.equipamento

                equipamento.regional = transferencia.regional_destino

                equipamento.status = 'ATIVO'

                equipamento.save(
                    update_fields=[
                        'regional',
                        'status'
                    ]
                )

                Historico.objects.create(
                    equipamento=equipamento,
                    tipo_acao='TRANSFERENCIA_RECEBIDA',
                    usuario=request.user,
                    detalhes={
                        'transferencia_id': transferencia.id,
                        'origem': transferencia.regional_origem.nome,
                        'destino': transferencia.regional_destino.nome,
                    }
                )

            transferencia.status = 'CONCLUIDA'
            transferencia.data_recebimento = timezone.now()
            transferencia.save()

            if transferencia.alocacao:

                item_solicitacao = transferencia.alocacao.item

                item_solicitacao.atendido += itens.count()

                item_solicitacao.save(
                    update_fields=['atendido']
                )

                solicitacao = item_solicitacao.solicitacao

                pendentes = sum(
                    i.pendente
                    for i in solicitacao.itens.all()
                )

                if pendentes <= 0:

                    solicitacao.status = 'FINALIZADO'
                    solicitacao.save(
                        update_fields=['status']
                    )

        messages.success(
            request,
            f'Transferência #{transferencia.id} recebida com sucesso.'
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
def editar_equipamento(request, equipamento_id):

    equipamento = get_object_or_404(
        Equipamento,
        id=equipamento_id
    )

    if request.method != 'POST':
        return redirect('estoque')

    senha_confirmacao = request.POST.get(
        'senha_confirmacao'
    )

    if not request.user.check_password(
        senha_confirmacao
    ):

        messages.error(
            request,
            'Senha inválida.'
        )

        return redirect(request.META.get('HTTP_REFERER'))

    patrimonio = request.POST.get(
        'patrimonio',
        ''
    ).strip()

    numero_serie = request.POST.get(
        'numero_serie',
        ''
    ).strip()

#    status = request.POST.get(
#        'status',
#        ''
#    ).strip()

    observacao = request.POST.get(
        'observacao_edicao',
        ''
    ).strip()

    foto = request.FILES.get('foto')

    equipamento.patrimonio = patrimonio
    equipamento.numero_serie = numero_serie

#    if status:
#        equipamento.status = status

    if foto:
        equipamento.foto = foto

    equipamento.save()

    Historico.objects.create(
        equipamento=equipamento,
        usuario=request.user,
        tipo_acao='edicao',
        detalhes={
            'observacao': observacao,
            'patrimonio': patrimonio,
            'numero_serie': numero_serie,
#            'status': status,
        }
    )

    messages.success(
        request,
        'Equipamento atualizado com sucesso.'
    )

    return redirect(
        request.META.get('HTTP_REFERER')
    )