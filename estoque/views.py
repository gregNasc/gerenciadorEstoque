from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.decorators import login_required, permission_required
from django.views.decorators.cache import cache_page
import csv
from django.db import transaction
from .forms import EquipamentoForm
from django.http import HttpResponse
from .models import (Produto, Equipamento, Transferencia, Sick, Historico, Base, Perfil, Empresa) #Regional
from .utils import filtrar_por_empresa, qs_equipamentos, qs_historico, qs_bases
from django.db.models import Count, Q, F
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from .decorators import role_required
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .utils import EstoqueService
from .security import secure_queryset
from estoque.services.transferencia_services import gerar_transferencias_da_solicitacao



# ----------------- DASHBOARD -----------------
@login_required
@cache_page(60 * 5)
def index(request):
    equipamentos = secure_queryset(
        Equipamento.objects.select_related('regional', 'produto'),
        request.user
    )

    # Configuração das categorias
    categorias_config = {
        'Coletores': {
            'keywords': ['coletor', 'mobydata', 'mc-65', 'ranger 2k', 'scorpio'],
            'icone': 'bi-upc-scan'
        },
        'Impressoras': {
            'keywords': ['impressora', 'hp', 'brother', 'samsung', 'xerox', 'pantum'],
            'icone': 'bi-printer'
        },
        'Notebooks': {
            'keywords': ['notebook', 'positivo', 'dell', 'lenovo', 'hp', 'samsung'],
            'icone': 'bi-laptop'
        },
        'Routers': {
            'keywords': ['router', 'roteador', 'switch', 'tp-link', 'mikrotik'],
            'icone': 'bi-wifi'
        }
    }

    # Filtros recebidos
    categoria = request.GET.get('categoria')
    produto_id = request.GET.get('produto')
    regional_id = request.GET.get('regional')

    # Aplica filtro de categoria (afeta equipamentos para tudo)
    if categoria:
        equipamentos = equipamentos.filter(produto__categoria=categoria)

    # Aplica filtros de produto e regional
    if produto_id and produto_id.isdigit():
        equipamentos = equipamentos.filter(produto_id=produto_id)
    if regional_id and regional_id.isdigit():
        equipamentos = equipamentos.filter(regional_id=regional_id)


    # CARDS SUPERIORES (KPIs dinâmicos)

    produtos_na_categoria = []
    if categoria and categoria in categorias_config:
        # Exibe os modelos específicos da categoria selecionada
        produtos_agrupados = equipamentos.values(
            'produto__id', 'produto__descricao'
        ).annotate(
            total=Count('id'),
            ativos=Count('id', filter=Q(status='ATIVO')),
            sick=Count('id', filter=Q(status='SICK')),
        ).order_by('produto__descricao')
        for p in produtos_agrupados:
            produtos_na_categoria.append({
                'id': p['produto__id'],
                'nome': p['produto__descricao'],
                'total': p['total'],
                'ativos': p['ativos'],
                'sick': p['sick'],
            })
    else:
        # Exibe as 4 categorias
        for tipo, config in categorias_config.items():
            query = Q()
            for kw in config['keywords']:
                query |= Q(produto__descricao__icontains=kw)
            equip_tipo = equipamentos.filter(query)
            produtos_na_categoria.append({
                'id': tipo,
                'nome': tipo,
                'total': equip_tipo.count(),
                'ativos': equip_tipo.filter(status='ATIVO').count(),
                'sick': equip_tipo.filter(status='SICK').count(),
                'icone': config['icone']
            })


    # CARDS REGIONAIS
    regionais_ids = equipamentos.values_list('regional_id', flat=True).distinct()
    regionais_lista = Base.objects.filter(id__in=regionais_ids).order_by('nome')

    kpis_regionais = []
    for regional in regionais_lista:
        equip_regional = equipamentos.filter(regional=regional)
        total_regional = equip_regional.count()
        ativos_regional = equip_regional.filter(status='ATIVO').count()
        sick_regional = equip_regional.filter(status='SICK').count()

        regional_data = {
            'regional__id': regional.id,
            'regional__nome': regional.nome,
            'total': total_regional,
            'ativos': ativos_regional,
            'sick': sick_regional,
            'disponibilidade': round((ativos_regional / total_regional * 100), 2) if total_regional else 0,
        }

        if categoria and categoria in categorias_config:
            # Mostra produtos detalhados (modelos) dentro da categoria para esta regional
            produtos_detalhados = equip_regional.values('produto__id', 'produto__descricao').annotate(
                total=Count('id'),
                ativos=Count('id', filter=Q(status='ATIVO')),
                sick=Count('id', filter=Q(status='SICK')),
            ).order_by('produto__descricao')
            regional_data['produtos_detalhados'] = list(produtos_detalhados)
        else:
            # Mostra resumo das 4 categorias
            produtos = {}
            for tipo, config in categorias_config.items():
                query = Q()
                for kw in config['keywords']:
                    query |= Q(produto__descricao__icontains=kw)
                equip_tipo = equip_regional.filter(query)
                produtos[tipo] = {
                    'total': equip_tipo.count(),
                    'ativos': equip_tipo.filter(status='ATIVO').count(),
                    'sick': equip_tipo.filter(status='SICK').count(),
                }
            regional_data['produtos'] = produtos

        kpis_regionais.append(regional_data)


    # Produtos disponíveis (filtrados pela categoria)
    produtos_lista = Produto.objects.all()
    if categoria:
        produtos_lista = produtos_lista.filter(categoria=categoria)

    # Regionais para o select (todas, sem filtro)
    regionais_select = Base.objects.all().order_by('nome')

    context = {
        'produtos_na_categoria': produtos_na_categoria,
        'categoria_selecionada': categoria,
        'kpis_regionais': kpis_regionais,
        'produtos_lista': produtos_lista,
        'regionais': regionais_select,
        'filtro_produto_id': produto_id,
        'filtro_regional_id': regional_id,
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
    )
    equipamentos = equipamentos.filter(regional_id=regional_id)


    categorias = {
        'Coletores': ['Coletor', 'MobyData', 'MC-65', 'Ranger 2K', 'MovFast', 'Coletor de Dados'],
        'Impressoras': ['Impressora', 'HP', 'Brother', 'Samsung', 'Xerox', 'Pantum', 'Argox', 'Zebra', 'Lexmark'],
        'Notebooks': ['Notebook', 'Laptop', 'Dell', 'LG', 'Samsung', 'Positivo', 'Compac'],
        'Routers': ['Router', 'Roteador', 'Switch', 'TP-Link', 'Mikrotik']
    }

    produtos_detalhados = []

    for categoria, keywords in categorias.items():
        query = Q()
        for keyword in keywords:
            query |= Q(produto__descricao__icontains=keyword)

        equip_categoria = equipamentos.filter(query)

        if equip_categoria.exists():
            produtos_agrupados = equip_categoria.values(
                'produto__id',
                'produto__descricao'
            ).annotate(
                total=Count('id'),
                ativos=Count('id', filter=Q(status='ATIVO')),
                sick=Count('id', filter=Q(status='SICK')),
                transferencia=Count('id', filter=Q(status='TRANSFERENCIA')),
                manutencao=Count('id', filter=Q(status='MANUTENCAO')),
            ).order_by('produto__descricao')

            produtos_com_equipamentos = []
            for produto in produtos_agrupados:
                equip_lista = equip_categoria.filter(produto_id=produto['produto__id']).values(
                    'id', 'numero_serie', 'patrimonio', 'status', 'responsavel'
                ).order_by('status', 'numero_serie')

                produtos_com_equipamentos.append({
                    'id': produto['produto__id'],
                    'nome': produto['produto__descricao'],
                    'total': produto['total'],
                    'ativos': produto['ativos'],
                    'sick': produto['sick'],
                    'transferencia': produto['transferencia'],
                    'manutencao': produto['manutencao'],
                    'equipamentos': list(equip_lista)
                })

            produtos_detalhados.append({
                'categoria': categoria,
                'produtos': produtos_com_equipamentos
            })

    kpis_regional = EstoqueService.get_kpis_gerais(equipamentos)
    regional = Base.objects.only('id', 'nome').get(id=regional_id)

    return JsonResponse({
        'categorias': produtos_detalhados,
        'regional_id': regional.id,
        'regional_nome': regional.nome,
        'total_regional': kpis_regional['total'],
        'disponibilidade_regional': EstoqueService.get_disponibilidade(equipamentos),
    })

@login_required
@role_required('admin', 'gestor')
def api_regionais_produto(request, produto_id):
    dados = (
        Equipamento.objects
        .filter(produto_id=produto_id)
        .values('regional__id', 'regional__nome')
        .annotate(total=Count('id'))
        .order_by('regional__nome')
    )

    return JsonResponse({
        'regionais': list(dados)
    })

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

    # Calcula usando o service
    kpis_geral = EstoqueService.get_kpis_gerais(equipamentos)

    # Calcula soma das regionais
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

    # Verifica consistência
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
        transferencia=Count('id', filter=Q(status='TRANSFERENCIA')),
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

            equipamento = get_object_or_404(
                base_qs,
                id=request.POST.get('equipamento_id')
            )

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
        equipamento__produto_id=produto_id,
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
        acao = request.POST.get('acao')

        if acao == 'resolver' and sick_id:

            sick = get_object_or_404(
                Sick.objects.select_related('equipamento'),
                id=sick_id
            )

            if not perfil.is_admin and (
                not perfil.regional or
                sick.equipamento.regional_id not in perfil.regionais_ids
            ):
                messages.error(request, "Sem permissão.")
                return redirect('estoque:sick')

            sick.data_resolucao = timezone.now()
            sick.ativo = False
            sick.resolvido_por = request.user
            sick.save(update_fields=[
                'data_resolucao',
                'ativo',
                'resolvido_por'
            ])

            equipamento = sick.equipamento
            equipamento.status = 'ATIVO'
            equipamento.save(update_fields=['status'])

            messages.success(request, "SICK resolvido com sucesso.")

        return redirect('estoque:sick')

    qs = Sick.objects.select_related(
        'equipamento',
        'equipamento__produto',
        'resolvido_por'
    )

    if perfil.is_admin:
        sicks = qs
    else:
        if not perfil.regional:
            sicks = qs.none()
        else:
            sicks = qs.filter(
                equipamento__regional=perfil.regional
            )

    sicks = sicks.order_by('-data_ocorrencia')

    total_pendentes = sicks.filter(data_resolucao__isnull=True).count()
    total_resolvidos = sicks.filter(data_resolucao__isnull=False).count()

    return render(request, 'estoque/sick.html', {
        'sicks': sicks,
        'total_sick': total_pendentes,
        'total_pendentes': total_pendentes,
        'total_resolvidos': total_resolvidos,
    })

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
            descricao=descricao
        )

        Historico.objects.create(
            equipamento=equipamento,
            tipo_acao='STATUS',
            usuario=request.user,
            detalhes={'novo_status': 'SICK'}
        )

    return JsonResponse({'sucesso': True})

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
@role_required('admin', 'gestor')
def exportar_historico_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="historico_equipamentos.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Data', 'Equipamento', 'Número de Série', 'Patrimônio',
        'Tipo de Ação', 'Usuário', 'Detalhes'
    ])

    historicos = Historico.objects.select_related(
        'equipamento', 'equipamento__produto', 'usuario'
    ).order_by('-data')

    for h in historicos:
        writer.writerow([
            h.data.strftime('%d/%m/%Y %H:%M'),
            h.equipamento.produto.descricao,
            h.equipamento.numero_serie,
            h.equipamento.patrimonio,
            h.get_tipo_acao_display(),
            h.usuario.username if h.usuario else 'Sistema',
            str(h.detalhes)[:100]  # Limitar tamanho
        ])

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

# ----------------- TRANSFERÊNCIA  -----------------
@login_required
@role_required('admin', 'gestor')
def pode_transferir(equipamento):
    if equipamento.status == 'SICK':
        return False, 'SICK'

    if Transferencia.objects.filter(
        equipamento=equipamento,
        status='PENDENTE'
    ).exists():
        return False, 'PENDENTE'

    return True, None

@login_required
@role_required('gestor')
def criar_solicitacao(request):

    if request.method == 'POST':
        Solicitacao.objects.create(
            produto_id=request.POST.get('produto'),
            quantidade=request.POST.get('quantidade'),
            motivo=request.POST.get('motivo'),
            regional_solicitante=request.user.perfil.regionais.first(),
            criado_por=request.user
        )

        messages.success(request, "Solicitação enviada.")
        return redirect('estoque:index')

    return render(request, 'estoque/solicitar.html', {
        'produtos': Produto.objects.all()
    })

def iniciar_transferencia(equipamento, destino, user, solicitacao=None):
    transferencia = Transferencia.objects.create(
        solicitacao=solicitacao,
        equipamento=equipamento,
        regional_origem=equipamento.regional,
        regional_destino=destino,
        solicitado_por=user,
        status='PENDENTE'
    )

    equipamento.status = 'TRANSFERENCIA'
    equipamento.save(update_fields=['status'])

    return transferencia

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
@role_required('admin')
def caixa_solicitacoes(request):

    solicitacoes = Solicitacao.objects.filter(status='PENDENTE')

    return render(request, 'estoque/caixa_solicitacoes.html', {
        'solicitacoes': solicitacoes
    })

@login_required
@require_POST
@role_required('admin')
def aprovar_solicitacao(request, solicitacao_id):

    origem_id = request.POST.get('origem')

    solicitacao = get_object_or_404(Solicitacao, id=solicitacao_id)
    origem = get_object_or_404(Base, id=origem_id)

    with transaction.atomic():
        solicitacao.status = 'APROVADO'
        solicitacao.aprovado_por = request.user
        solicitacao.regional_origem = origem
        solicitacao.data_aprovacao = timezone.now()
        solicitacao.save()

        gerar_transferencias_da_solicitacao(
            solicitacao,
            origem,
            request.user
        )

    return JsonResponse({'sucesso': True})

@login_required
@role_required('gestor', 'operador')
def atender_solicitacao(request, solicitacao_id):

    solicitacao = get_object_or_404(Solicitacao, id=solicitacao_id)

    equipamentos = Equipamento.objects.filter(
        produto=solicitacao.produto,
        regional=solicitacao.regional_origem,
        status='ATIVO'
    )

    if request.method == 'POST':

        ids = request.POST.getlist('equipamentos')

        with transaction.atomic():
            for eid in ids:
                e = Equipamento.objects.select_for_update().get(id=eid)

                iniciar_transferencia(
                    equipamento=e,
                    destino=solicitacao.regional_solicitante,
                    user=request.user,
                    solicitacao=solicitacao
                )

        return redirect('estoque:index')

    return render(request, 'estoque/atender_solicitacao.html', {
        'equipamentos': equipamentos,
        'solicitacao': solicitacao
    })

@login_required
@require_POST
@role_required('admin', 'gestor')
def transferir_em_lote(request):

    data = json.loads(request.body)

    ids = data.get('equipamentos', [])
    destino = get_object_or_404(Base, id=data.get('destino'))

    if not ids:
        return JsonResponse({'erro': 'Nenhum equipamento selecionado'}, status=400)

    bloqueados = []

    with transaction.atomic():

        equipamentos = secure_queryset(
            Equipamento.objects.select_for_update(),
            request.user,
            'regional__empresa'
        ).filter(id__in=ids)

        for e in equipamentos:

            pode, motivo = pode_transferir(e)

            if not pode:
                bloqueados.append({
                    'serie': e.numero_serie,
                    'motivo': motivo
                })
                continue

            iniciar_transferencia(e, destino, request.user)

    return JsonResponse({
        'sucesso': True,
        'bloqueados': bloqueados
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
        secure_queryset(
            Transferencia.objects.select_related('equipamento'),
            request.user,
            'equipamento__regional__empresa'
        ),
        id=transferencia_id
    )
    perfil = request.user.perfil

    if perfil.role != 'admin' and not perfil.regionais.filter(id=transferencia.regional_destino.id).exists():
        messages.error(request, "Sem permissão.")
        return redirect('estoque:index')

    if transferencia.status != 'PENDENTE':
        messages.error(request, "Transferência inválida.")
        return redirect('estoque:lista_transferencias')

    if request.method == 'POST':
        with transaction.atomic():
            transferencia = Transferencia.objects.select_for_update().get(id=transferencia.id)
            finalizar_transferencia(transferencia, request.user)

        messages.success(request, "Transferência recebida.")
        return redirect('estoque:index')

    return render(request, 'estoque/receber_transferencia.html', {
        'transferencia': transferencia
    })

@login_required
def receber_transferencia_lote(request, solicitacao_id):

    transferencias = Transferencia.objects.filter(
        solicitacao_id=solicitacao_id,
        status='PENDENTE'
    )

    if request.method == 'POST':

        ids = request.POST.getlist('transferencias')

        with transaction.atomic():

            for tid in ids:
                t = Transferencia.objects.select_for_update().get(id=tid)
                finalizar_transferencia(t, request.user)

    return render(request, 'estoque/receber_lote.html', {
        'transferencias': transferencias
    })

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
        equipamento.status = 'ATIVO'  # 🔥 CORREÇÃO CRÍTICA
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

    qs = Transferencia.objects.select_related(
        'equipamento',
        'equipamento__produto',
        'regional_origem',
        'regional_destino',
        'solicitado_por',
        'recebido_por'
    ).order_by('-data_envio')  # ← corrigido

    if perfil.role != 'admin':
        qs = qs.filter(
            Q(regional_destino__in=perfil.regionais_ids) |
            Q(regional_origem=perfil.regionais.first())  # cuidado: veja nota abaixo
        )

    hoje = timezone.now().date()
    qs = list(qs)

    for t in qs:
        t.pode_receber = (
            t.status == 'PENDENTE' and
            (
                perfil.role == 'admin' or
                t.regional_destino.id in perfil.regionais_ids
            )
        )
        base = t.data_recebimento.date() if t.data_recebimento else hoje
        t.dias = (base - t.data_envio.date()).days  # ← corrigido

    return render(request, 'estoque/transferencia/listar.html', {
        'transferencias': qs
    })

@login_required
@role_required('admin', 'gestor')
def equipamentos_por_regional(request, produto_id, regional_id):
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
                'status': e.status
            }
            for e in equipamentos
        ],
        'regionais': list(
            Base.objects.exclude(id=regional_id).values('id', 'nome')
        )
    }

    return JsonResponse(data)