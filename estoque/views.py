from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from django.core.paginator import Paginator
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors
from openpyxl import Workbook
from .services.emprestimo_service import EmprestimoService
from .services.comunicado_service import ComunicadoService
from .services.sick_service import SickService
from .services.assistente_operacional_service import AssistenteOperacionalService
from .services.manual_service import ManualService
from .services.assistente.response_builder import construir_erro, construir_resposta
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
from django.db.models import Count, Q, F, Prefetch
from django.utils.dateparse import parse_date
from estoque.models import Equipamento
from insumos.models import ChecklistDiario
from insumos.models import ItemChecklist, LoteTag, RoloTag
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
import logging
from uuid import uuid4

logger = logging.getLogger(__name__)
from collections import defaultdict
from .services.estoque_service import get_estoque_por_produto
from django.contrib.auth import authenticate
from auditorias.services.visibilidade_estoque_service import VisibilidadeEstoqueAuditoriaService


def _normalizar_nome_base(valor):
    return re.sub(r'\s+', ' ', str(valor or '').strip()).upper()

def _bases_agrupadas_por_nome(queryset):
    bases_por_nome = OrderedDict()
    for base in queryset.select_related('empresa').order_by('nome', 'id'):
        chave = _normalizar_nome_base(base.nome)
        if not chave:
            continue
        bases_por_nome.setdefault(chave, []).append(base)
    return bases_por_nome

def _bases_unicas_por_nome(queryset):
    return [bases[0] for bases in _bases_agrupadas_por_nome(queryset).values()]

def _base_contexto_usuario(request):
    """Resolve e persiste uma base selecionada sem confiar apenas no cliente."""
    perfil = request.user.perfil
    base_id = (
        request.GET.get('regional') or
        request.POST.get('regional') or
        request.session.get('estoque_base_contexto_id')
    )
    if not base_id and not perfil.is_admin and perfil.regionais.count() == 1:
        base_id = perfil.regionais.values_list('id', flat=True).first()
    if not str(base_id or '').isdigit():
        return None

    bases = Base.objects.select_related('empresa')
    if not perfil.is_admin:
        bases = bases.filter(pk__in=perfil.regionais.values_list('pk', flat=True))
    base = bases.filter(pk=base_id).first()
    if base:
        request.session['estoque_base_contexto_id'] = base.pk
    return base


def _base_em_auditoria(base_id):
    return VisibilidadeEstoqueAuditoriaService.base_bloqueada(base_id)


def _resposta_base_em_auditoria():
    return JsonResponse(
        {
            'erro': VisibilidadeEstoqueAuditoriaService.MENSAGEM,
            'codigo': 'estoque_oculto_auditoria',
        },
        status=423,
    )


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
    estoque_oculto_auditoria = bool(
        regional_id and regional_id.isdigit() and _base_em_auditoria(regional_id)
    )
    inventory_id = request.GET.get('inventory')
    finalidade = request.GET.get('finalidade', '').strip().upper()

    if not perfil.is_admin:
        inventory_id = str(perfil.empresa_id) if perfil.empresa_id else ''

    if inventory_id and inventory_id.isdigit():
        equipamentos = equipamentos.filter(
            regional__empresa_id=inventory_id
        )

    if categoria:
        equipamentos = equipamentos.filter(produto__categoria=categoria)

    if produto_id and produto_id.isdigit():
        equipamentos = equipamentos.filter(produto_id=produto_id)

    if finalidade in Equipamento.Finalidade.values:
        equipamentos = equipamentos.filter(finalidade=finalidade)
    else:
        finalidade = ''

    regional_id = request.GET.get('regional')
    if regional_id and regional_id.isdigit():
        if not perfil.is_admin and not perfil.regionais.filter(id=regional_id).exists():
            messages.error(request, "Acesso negado a esta regional.")
            return redirect('estoque:index')
        equipamentos = equipamentos.filter(regional_id=regional_id)
        request.session['estoque_base_contexto_id'] = int(regional_id)

    # KPI SUPERIOR
    total_filtrado = equipamentos.count()
    ativos_filtrado = equipamentos.filter(
        status='ATIVO', finalidade=Equipamento.Finalidade.OPERACIONAL
    ).count()
    administrativos_filtrado = equipamentos.filter(
        finalidade=Equipamento.Finalidade.ADMINISTRATIVO
    ).exclude(status='BAIXA').count()
    sick_filtrado = equipamentos.filter(status='SICK').count()
    inativos_filtrado = equipamentos.filter(status='INATIVO').count()
    manutencao_filtrado = equipamentos.filter(status='MANUTENCAO').count()
    disponibilidade_filtrada = round((ativos_filtrado / total_filtrado * 100), 2) if total_filtrado else 0

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
                ativos=Count('id', filter=Q(
                    status='ATIVO', finalidade=Equipamento.Finalidade.OPERACIONAL
                )),
                administrativos=Count('id', filter=Q(
                    finalidade=Equipamento.Finalidade.ADMINISTRATIVO
                ) & ~Q(status='BAIXA')),
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
                ativos=Count('id', filter=Q(
                    status='ATIVO', finalidade=Equipamento.Finalidade.OPERACIONAL
                )),
                administrativos=Count('id', filter=Q(
                    finalidade=Equipamento.Finalidade.ADMINISTRATIVO
                ) & ~Q(status='BAIXA')),
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
    regionais_por_nome = _bases_agrupadas_por_nome(Base.objects.filter(id__in=regionais_ids))

    kpis_regionais = []

    for bases_grupo in regionais_por_nome.values():
        regional = bases_grupo[0]
        bases_ids = [base.id for base in bases_grupo]
        equip_regional = equipamentos.filter(regional_id__in=bases_ids)

        total = equip_regional.count()
        ativos = equip_regional.filter(
            status='ATIVO', finalidade=Equipamento.Finalidade.OPERACIONAL
        ).count()
        administrativos = equip_regional.filter(
            finalidade=Equipamento.Finalidade.ADMINISTRATIVO
        ).exclude(status='BAIXA').count()
        sick = equip_regional.filter(status='SICK').count()
        inativos = equip_regional.filter(status='INATIVO').count()

        regional_data = {
            'regional__id': regional.id,
            'regional__nome': regional.nome,
            'total': total,
            'ativos': ativos,
            'administrativos': administrativos,
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
                ativos=Count('id', filter=Q(
                    status='ATIVO', finalidade=Equipamento.Finalidade.OPERACIONAL
                )),
                administrativos=Count('id', filter=Q(
                    finalidade=Equipamento.Finalidade.ADMINISTRATIVO
                ) & ~Q(status='BAIXA')),
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
                    ativos=Count('id', filter=Q(
                        status='ATIVO', finalidade=Equipamento.Finalidade.OPERACIONAL
                    )),
                    administrativos=Count('id', filter=Q(
                        finalidade=Equipamento.Finalidade.ADMINISTRATIVO
                    ) & ~Q(status='BAIXA')),
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
                    'administrativos': produtos_dict.get(categoria, {}).get('administrativos', 0),
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

    if perfil.is_admin:
        regionais_select = Base.objects.all()

        if inventory_id and inventory_id.isdigit():
            regionais_select = regionais_select.filter(
                empresa_id=inventory_id
            )
    else:
        regionais_select = perfil.regionais.filter(
            empresa=perfil.empresa
        )

    regionais_select = _bases_unicas_por_nome(regionais_select)
    empresas = (
        Empresa.objects.all().order_by('nome')
        if perfil.is_admin
        else Empresa.objects.filter(id=perfil.empresa_id)
    )

    context = {
        'produtos_na_categoria': produtos_na_categoria,
        'kpis_totais': {
            'total': total_filtrado,
            'ativos': ativos_filtrado,
            'administrativos': administrativos_filtrado,
            'sick': sick_filtrado,
            'inativos': inativos_filtrado,
            'manutencao': manutencao_filtrado,
            'disponibilidade': disponibilidade_filtrada,
        },
        'categoria_selecionada': categoria,
        'kpis_regionais': kpis_regionais,
        'produtos_lista': produtos_lista,
        'regionais': regionais_select,
        'filtro_produto_id': produto_id,
        'filtro_regional_id': regional_id,
        'empresas': empresas,
        'filtro_inventory_id': inventory_id,
        'filtro_finalidade': finalidade,
        'finalidade_choices': Equipamento.Finalidade.choices,
        'estoque_oculto_auditoria': estoque_oculto_auditoria,
        'mensagem_auditoria': VisibilidadeEstoqueAuditoriaService.MENSAGEM,
    }

    return render(request, 'estoque/index.html', context)

@login_required
@role_required('admin', 'gestor')
def assistente_operacional(request):
    resultado = None
    pergunta = ''

    if request.method == 'POST':
        ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        if request.POST.get('acao') == 'limpar_contexto':
            request.session.pop('assistente_operacional_contexto', None)
            resposta = construir_resposta({
                'resposta': 'Conversa reiniciada.',
                'tipo': 'texto',
            })
            return JsonResponse(resposta) if ajax else redirect('estoque:assistente_operacional')

        pergunta = request.POST.get('pergunta', '').strip()
        if not pergunta:
            resultado = construir_erro(
                'Digite uma pergunta antes de enviar.',
                codigo='pergunta_vazia',
                status=400,
            )
            if ajax:
                return JsonResponse(resultado, status=400)
        else:
            contexto = request.session.get('assistente_operacional_contexto', {})
            try:
                resposta_servico = AssistenteOperacionalService.responder(
                    request.user,
                    pergunta,
                    contexto=contexto,
                )
                request.session['assistente_operacional_contexto'] = resposta_servico.get('contexto', {})
                resultado = construir_resposta(resposta_servico)
            except PermissionDenied:
                resultado = construir_erro(
                    'Você não possui permissão para consultar essas informações.',
                    codigo='permissao',
                    status=403,
                )
                if ajax:
                    return JsonResponse(resultado, status=403)
            except Exception:
                logger.exception(
                    'Falha controlada ao processar consulta da Tory para user_id=%s',
                    request.user.pk,
                )
                resultado = construir_erro(
                    'Não foi possível processar a consulta neste momento.',
                    codigo='processamento',
                    status=500,
                )
                if ajax:
                    return JsonResponse(resultado, status=500)

        if ajax:
            return JsonResponse(resultado)

    return render(
        request,
        'estoque/assistente_operacional.html',
        {
            'pergunta': pergunta,
            'resultado': resultado,
        }
    )

@login_required
def manuais_view(request):
    filtros = {
        'q': request.GET.get('q', '').strip(),
        'categoria': request.GET.get('categoria', '').strip(),
        'idioma': request.GET.get('idioma', '').strip(),
    }
    catalogo_completo = ManualService.listar()
    manuais = ManualService.listar(
        termo=filtros['q'],
        categoria=filtros['categoria'],
        idioma=filtros['idioma'],
    )
    return render(
        request,
        'estoque/manuais.html',
        {
            'manuais': manuais,
            'estatisticas': ManualService.estatisticas(catalogo_completo),
            'categorias': sorted({item['categoria'] for item in catalogo_completo}),
            'filtros': filtros,
        },
    )

@login_required
def api_kpis_json(request):
    equipamentos = secure_queryset(
        Equipamento.objects.select_related('regional', 'produto'),
        request.user
    )

    produto_id = request.GET.get('produto')
    regional_id = request.GET.get('regional')

    if regional_id and regional_id.isdigit() and _base_em_auditoria(regional_id):
        return _resposta_base_em_auditoria()

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

    if _base_em_auditoria(regional_id):
        return _resposta_base_em_auditoria()

    equipamentos = secure_queryset(
        Equipamento.objects.select_related('regional', 'produto'),
        request.user
    ).filter(regional_id__in=[regional_id])

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
            ativos=Count('id', filter=Q(
                status='ATIVO', finalidade=Equipamento.Finalidade.OPERACIONAL
            )),
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
    ativos = equipamentos.filter(
        status='ATIVO', finalidade=Equipamento.Finalidade.OPERACIONAL
    ).count()

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

                # VALIDAÇÕES
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

                # REGRA REGIONAL
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

                # CRIA USUÁRIO
                user = User.objects.create_user(
                    username=username,
                    password=password,
                    first_name=first_name,
                    email=email,
                    is_active=True
                )

                # PERFIL
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

@login_required
@role_required('admin')
def gerenciar_usuarios(request):
    from django.contrib.auth.models import Group, User
    from .models import Perfil, Empresa, Base
    from django.db import transaction
    from insumos.constants import GruposInsumos

    perfis_acesso = [
        {'value': 'operador', 'label': 'Operador', 'role': Perfil.Role.OPERADOR, 'grupo': '', 'global': False},
        {'value': 'gestor', 'label': 'Gestor', 'role': Perfil.Role.GESTOR, 'grupo': '', 'global': False},
        {'value': 'admin', 'label': 'Administrador', 'role': Perfil.Role.ADMIN, 'grupo': '', 'global': True},
        {'value': 'planejamento', 'label': 'Planejamento', 'role': Perfil.Role.OPERADOR, 'grupo': GruposInsumos.PLANEJAMENTO, 'global': True},
        {'value': 'compras', 'label': 'Compras', 'role': Perfil.Role.OPERADOR, 'grupo': GruposInsumos.COMPRAS, 'global': True},
        {'value': 'financeiro', 'label': 'Financeiro', 'role': Perfil.Role.OPERADOR, 'grupo': GruposInsumos.FINANCEIRO, 'global': True},
        {'value': 'executivo', 'label': 'Executivo', 'role': Perfil.Role.OPERADOR, 'grupo': GruposInsumos.EXECUTIVO, 'global': True},
    ]
    perfis_acesso_map = {perfil['value']: perfil for perfil in perfis_acesso}

    if request.method == 'POST':
        try:
            with transaction.atomic():
                usuario_id = request.POST.get('usuario_id', '').strip()
                username = request.POST.get('username', '').strip()
                password = request.POST.get('password', '')
                first_name = request.POST.get('first_name', '').strip()
                last_name = request.POST.get('last_name', '').strip()
                email = request.POST.get('email', '').strip()
                perfil_acesso = request.POST.get('perfil_acesso', 'operador')
                perfil_config = perfis_acesso_map.get(perfil_acesso)
                role = perfil_config['role'] if perfil_config else Perfil.Role.OPERADOR
                acesso_global = bool(perfil_config and perfil_config['global'])
                empresa_id = request.POST.get('empresa', '').strip()
                regionais_ids = request.POST.getlist('regionais')
                bases_checklist_ids = request.POST.getlist('bases_checklist')
                telefone = request.POST.get('telefone', '').strip()
                telefone_alternativo = request.POST.get('telefone_alternativo', '').strip()
                is_active = request.POST.get('is_active') == 'on'
                editando = bool(usuario_id)

                if not username:
                    messages.error(request, "Informe o nome de usuario.")
                    return redirect('estoque:cadastrar_usuario')

                if not perfil_config:
                    messages.error(request, "Tipo de acesso invalido.")
                    return redirect('estoque:cadastrar_usuario')

                if not editando and not password:
                    messages.error(request, "Informe a senha.")
                    return redirect('estoque:cadastrar_usuario')

                if password and len(password) < 6:
                    messages.error(request, "Senha minima de 6 caracteres.")
                    return redirect('estoque:cadastrar_usuario')

                usuarios_mesmo_login = User.objects.filter(username=username)
                if editando:
                    usuarios_mesmo_login = usuarios_mesmo_login.exclude(id=usuario_id)
                if usuarios_mesmo_login.exists():
                    messages.error(request, f"Usuario '{username}' ja existe.")
                    return redirect('estoque:cadastrar_usuario')

                usuarios_mesmo_email = User.objects.filter(email=email)
                if editando:
                    usuarios_mesmo_email = usuarios_mesmo_email.exclude(id=usuario_id)
                if email and usuarios_mesmo_email.exists():
                    messages.error(request, f"E-mail '{email}' ja esta em uso.")
                    return redirect('estoque:cadastrar_usuario')

                empresa = None
                regionais = Base.objects.none()
                bases_checklist = Base.objects.none()

                if not acesso_global:
                    if not empresa_id:
                        messages.error(request, "Selecione a empresa do usuario.")
                        return redirect('estoque:cadastrar_usuario')

                    empresa = get_object_or_404(Empresa, id=empresa_id)

                    if not regionais_ids:
                        messages.error(request, "Selecione ao menos uma base.")
                        return redirect('estoque:cadastrar_usuario')

                    regionais = Base.objects.filter(id__in=regionais_ids, empresa=empresa).select_related('empresa')

                    if regionais.count() != len(set(regionais_ids)):
                        messages.error(request, "Existe base selecionada fora da empresa informada.")
                        return redirect('estoque:cadastrar_usuario')

                    if bases_checklist_ids:
                        bases_checklist = Base.objects.filter(
                            id__in=bases_checklist_ids,
                            empresa=empresa
                        ).select_related('empresa')

                        if bases_checklist.count() != len(set(bases_checklist_ids)):
                            messages.error(request, "Existe base de checklist fora da empresa informada.")
                            return redirect('estoque:cadastrar_usuario')

                        regionais_ids_set = {str(base_id) for base_id in regionais.values_list('id', flat=True)}
                        bases_checklist_ids_set = {str(base_id) for base_id in bases_checklist.values_list('id', flat=True)}
                        if not bases_checklist_ids_set.issubset(regionais_ids_set):
                            messages.error(request, "As bases do checklist precisam fazer parte das bases de acesso.")
                            return redirect('estoque:cadastrar_usuario')

                if editando:
                    user = get_object_or_404(User, id=usuario_id)
                    if user == request.user and role != Perfil.Role.ADMIN:
                        messages.error(request, "Voce nao pode remover seu proprio acesso de administrador.")
                        return redirect('estoque:cadastrar_usuario')
                    if user == request.user and not is_active:
                        messages.error(request, "Voce nao pode desativar o proprio usuario.")
                        return redirect('estoque:cadastrar_usuario')
                else:
                    user = User()

                user.username = username
                user.first_name = first_name
                user.last_name = last_name
                user.email = email
                user.is_active = is_active
                if password:
                    user.set_password(password)
                user.save()

                perfil, _ = Perfil.objects.get_or_create(
                    user=user,
                    defaults={'role': Perfil.Role.OPERADOR}
                )
                perfil.role = role
                perfil.empresa = empresa if not acesso_global else None
                perfil.telefone = telefone
                perfil.telefone_alternativo = telefone_alternativo
                perfil.save()

                grupos_insumos = Group.objects.filter(name__in=GruposInsumos.TODOS)
                user.groups.remove(*grupos_insumos)
                if perfil_config['grupo']:
                    grupo, _ = Group.objects.get_or_create(name=perfil_config['grupo'])
                    user.groups.add(grupo)

                if not acesso_global:
                    perfil.regionais.set(regionais)
                    perfil.bases_checklist.set(bases_checklist)
                else:
                    perfil.regionais.clear()
                    perfil.bases_checklist.clear()

                acao = "atualizado" if editando else "criado"
                messages.success(request, f"Usuario '{username}' {acao} com sucesso!")
                return redirect('estoque:cadastrar_usuario')

        except Exception as e:
            messages.error(request, f"Erro ao salvar usuario: {str(e)}")
            return redirect('estoque:cadastrar_usuario')

    context = {
        'empresas': Empresa.objects.all().order_by('nome'),
        'regionais': Base.objects.select_related('empresa').all().order_by('empresa__nome', 'nome'),
        'roles': Perfil.Role.choices,
        'perfis_acesso': perfis_acesso,
        'usuarios': (
            User.objects
            .select_related('perfil', 'perfil__empresa')
            .prefetch_related('perfil__regionais', 'perfil__bases_checklist')
            .order_by('first_name', 'username')
        ),
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
    base_selecionada = _base_contexto_usuario(request)
    if request.method == 'POST':
        form = EquipamentoForm(
            request.POST, request.FILES, user=request.user,
            base_selecionada=base_selecionada,
        )
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
        form = EquipamentoForm(user=request.user, base_selecionada=base_selecionada)

    return render(request, 'estoque/cadastrar_equipamento.html', {
        'form': form,
        'base_selecionada': base_selecionada,
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
    estoque_oculto_auditoria = bool(
        regional_id and regional_id.isdigit() and _base_em_auditoria(regional_id)
    )

    if regional_id and regional_id.isdigit():

        equipamentos = equipamentos.filter(
            regional_id=regional_id
        )
        request.session['estoque_base_contexto_id'] = int(regional_id)

    total_estoque = equipamentos.count()
    ativos_estoque = equipamentos.filter(
        status='ATIVO', finalidade=Equipamento.Finalidade.OPERACIONAL
    ).count()
    administrativos_estoque = equipamentos.filter(
        finalidade=Equipamento.Finalidade.ADMINISTRATIVO
    ).exclude(status='BAIXA').count()
    sick_estoque = equipamentos.filter(status='SICK').count()
    manutencao_estoque = equipamentos.filter(status='MANUTENCAO').count()

    status_em_transito = [
        'PENDENTE',
        'ENVIADO',
        'EM_TRANSITO',
        'AGUARDANDO_RECEBIMENTO',
        'TRANSFERENCIA'
    ]

    produtos_agrupados = (
        equipamentos
        .values('produto__id', 'produto__descricao', 'produto__categoria')
        .annotate(
            total=Count('id'),

            ativos=Count(
                'id',
                filter=Q(
                    status='ATIVO', finalidade=Equipamento.Finalidade.OPERACIONAL
                )
            ),

            administrativos=Count(
                'id',
                filter=Q(finalidade=Equipamento.Finalidade.ADMINISTRATIVO) & ~Q(status='BAIXA')
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

    categorias_estoque = [
        {'nome': 'Coletores', 'total_modelos': 0},
        {'nome': 'Notebooks', 'total_modelos': 0},
        {'nome': 'Impressoras', 'total_modelos': 0},
        {'nome': 'Routers', 'total_modelos': 0},
    ]

    for categoria in categorias_estoque:
        categoria['total_modelos'] = sum(
            1
            for produto in produtos_processados
            if produto.get('produto__categoria') == categoria['nome']
        )

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
            'categorias_estoque': categorias_estoque,
            'regionais': regionais,
            'regional_selecionada': regional_id,
            'estoque_oculto_auditoria': estoque_oculto_auditoria,
            'mensagem_auditoria': VisibilidadeEstoqueAuditoriaService.MENSAGEM,
            'kpis_estoque': {
                'total': total_estoque,
                'ativos': ativos_estoque,
                'administrativos': administrativos_estoque,
                'sick': sick_estoque,
                'manutencao': manutencao_estoque,
                'disponibilidade': int((ativos_estoque / total_estoque) * 100) if total_estoque else 0,
            }
        }
    )


# ----------------- DETALHES DO PRODUTO -----------------
@login_required
@role_required('admin', 'gestor')
def detalhes_produto_view(request, produto_id, regional_id):

    perfil = request.user.perfil

    regional = get_object_or_404(Base, id=regional_id)
    produto = get_object_or_404(Produto, id=produto_id)

    if _base_em_auditoria(regional_id):
        messages.warning(request, VisibilidadeEstoqueAuditoriaService.MENSAGEM)
        return redirect(f"{reverse('estoque:estoque')}?regional={regional_id}")

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

        # SICK
        if acao == 'sick':
            messages.error(
                request,
                "Use a ação SICK do equipamento para informar categoria, motivo e observação.",
            )
            return redirect(request.path)

        # TRANSFERÊNCIA
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

    if regional_id and str(regional_id).isdigit() and _base_em_auditoria(regional_id):
        return _resposta_base_em_auditoria()

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
@role_required('admin', 'gestor', 'operador')
def sick_view(request):

    perfil = request.user.perfil

    pode_acessar = (
            perfil.is_admin or
            perfil.is_gestor or
            perfil.is_operador or
            pode_realizar_manutencao_sick(request.user)
    )

    if not pode_acessar:
        messages.error(request, "Sem permissão.")
        return redirect('estoque:index')

    if request.method == 'POST':

        acao = request.POST.get('acao', '').strip()
        if acao:
            sick_id = request.POST.get('sick_id')
            resultado = None
            try:
                if acao == 'atualizar_informacoes':
                    resultado = SickService.atualizar_informacoes(
                        sick_id=sick_id,
                        usuario=request.user,
                        categoria=request.POST.get('categoria'),
                        motivo=request.POST.get('motivo'),
                        observacao=request.POST.get('observacao'),
                    )
                elif acao == 'enviar_para_manutencao':
                    resultado = SickService.enviar_para_manutencao(
                        sick_id=sick_id,
                        usuario=request.user,
                        destino=request.POST.get('destino_manutencao'),
                        tipo_destino=(
                            request.POST.get('tipo_destino') or Sick.TipoDestino.MATRIZ
                        ),
                        transportadora=request.POST.get('transportadora_ou_portador'),
                        protocolo=request.POST.get('protocolo_envio'),
                        codigo_rastreio=request.POST.get('codigo_rastreio_envio'),
                        observacao=request.POST.get('observacao'),
                    )
                elif acao == 'confirmar_recebimento':
                    resultado = SickService.confirmar_recebimento(
                        sick_id=sick_id, usuario=request.user,
                        observacao=request.POST.get('observacao'),
                    )
                elif acao == 'iniciar_avaliacao':
                    resultado = SickService.iniciar_avaliacao(
                        sick_id=sick_id, usuario=request.user,
                        observacao=request.POST.get('observacao'),
                    )
                elif acao == 'iniciar_manutencao':
                    resultado = SickService.iniciar_manutencao(
                        sick_id=sick_id, usuario=request.user,
                        causa=request.POST.get('causa_identificada'),
                        diagnostico=request.POST.get('diagnostico'),
                        observacao=request.POST.get('observacao_tecnica'),
                        previsao_retorno=request.POST.get('previsao_retorno'),
                    )
                elif acao == 'concluir_manutencao':
                    resultado = SickService.concluir_manutencao(
                        sick_id=sick_id, usuario=request.user,
                        solucao=request.POST.get('solucao_aplicada'),
                        resultado=request.POST.get('resultado_manutencao'),
                        apto_retorno=request.POST.get('apto_retorno'),
                        observacao=request.POST.get('observacao'),
                    )
                elif acao == 'inativar_sem_reparo':
                    resultado = SickService.inativar_sem_reparo(
                        sick_id=sick_id, usuario=request.user,
                        motivo=request.POST.get('motivo_inativacao'),
                    )
                elif acao == 'confirmar_retorno':
                    resultado = SickService.confirmar_retorno(
                        sick_id=sick_id, usuario=request.user,
                        observacao=request.POST.get('observacao'),
                        codigo_rastreio_retorno=request.POST.get('codigo_rastreio_retorno'),
                    )
                else:
                    raise ValidationError('Ação de SICK inválida.')
            except (ValidationError, PermissionDenied, Sick.DoesNotExist) as exc:
                if isinstance(exc, ValidationError):
                    texto = '; '.join(exc.messages)
                else:
                    texto = str(exc)
                messages.error(request, texto)
            else:
                messages.success(request, 'Etapa do SICK atualizada com sucesso.')
            etapa_retorno = 'INATIVOS' if acao == 'inativar_sem_reparo' and resultado else (
                resultado.etapa if resultado else
                Sick.objects.filter(pk=sick_id).values_list('etapa', flat=True).first()
            )
            etapa_retorno = etapa_retorno or Sick.Etapa.IDENTIFICADO
            return redirect(
                f"{reverse('estoque:sick')}?etapa={etapa_retorno}&sick={sick_id}#sick-{sick_id}"
            )

        if request.POST.get('novo_status'):
            messages.error(request, 'O fluxo antigo foi desativado. Use a próxima etapa indicada.')
            return redirect('estoque:sick')

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
        'equipamento__regional__empresa',
        'resolvido_por',
        'enviado_manutencao_por',
        'recebido_manutencao_por',
        'avaliacao_iniciada_por',
        'manutencao_iniciada_por',
        'manutencao_concluida_por',
        'retorno_confirmado_por',
    ).prefetch_related(
        Prefetch(
            'equipamento__sicks',
            queryset=SickService.visiveis_para(request.user, Sick.objects.select_related(
                'resolvido_por', 'enviado_manutencao_por',
                'recebido_manutencao_por', 'avaliacao_iniciada_por',
                'manutencao_iniciada_por', 'manutencao_concluida_por',
                'retorno_confirmado_por',
            )).order_by('-data_ocorrencia'),
            to_attr='historico_sick_prefetch',
        ),
        Prefetch(
            'equipamento__historico_set',
            queryset=SickService.filtrar_historicos_visiveis(
                request.user,
                Historico.objects.select_related('usuario'),
            ).order_by('data'),
            to_attr='eventos_sick_prefetch',
        ),
    )

    sicks = SickService.visiveis_para(request.user, qs)

    situacao_filter = (
        request.GET.get('situacao') or request.GET.get('status') or ''
    ).strip().lower()
    produto_filter = request.GET.get('produto', '')
    categoria_filter = request.GET.get('categoria', '')
    regional_filter = request.GET.get('regional', '')
    busca = request.GET.get('q', '').strip()
    etapa_solicitada = request.GET.get('etapa', '').strip()
    etapa_filter = etapa_solicitada or (
        'TODOS' if situacao_filter else Sick.Etapa.IDENTIFICADO
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

    if busca:
        sicks = sicks.filter(
            Q(equipamento__produto__descricao__icontains=busca) |
            Q(equipamento__produto__fabricante__icontains=busca) |
            Q(equipamento__produto__modelo__icontains=busca) |
            Q(equipamento__numero_serie__icontains=busca) |
            Q(equipamento__patrimonio__icontains=busca) |
            Q(equipamento__codigo__icontains=busca) |
            Q(equipamento__regional__nome__icontains=busca) |
            Q(equipamento__regional__empresa__nome__icontains=busca)
        )

    sicks_base_filtros = sicks

    total_sick = sicks_base_filtros.filter(
        ativo=True
    ).count()

    total_pendentes = sicks_base_filtros.filter(
        ativo=True,
        etapa__in=[
            Sick.Etapa.IDENTIFICADO,
            Sick.Etapa.EM_TRANSITO,
            Sick.Etapa.RECEBIDO,
            Sick.Etapa.EM_AVALIACAO,
            Sick.Etapa.AGUARDANDO_RETORNO,
        ]
    ).count()

    total_manutencao = sicks_base_filtros.filter(
        etapa=Sick.Etapa.EM_MANUTENCAO
    ).count()

    total_inativos = sicks_base_filtros.filter(
        status_final__in=['INATIVO', 'SUCATA']
    ).count()

    total_resolvidos = sicks_base_filtros.filter(
        etapa=Sick.Etapa.FINALIZADO
    ).count()

    total_identificados = sicks_base_filtros.filter(etapa=Sick.Etapa.IDENTIFICADO).count()
    total_em_transito = sicks_base_filtros.filter(etapa=Sick.Etapa.EM_TRANSITO).count()
    total_recebidos = sicks_base_filtros.filter(etapa=Sick.Etapa.RECEBIDO).count()
    total_em_avaliacao = sicks_base_filtros.filter(etapa=Sick.Etapa.EM_AVALIACAO).count()
    total_aguardando_retorno = sicks_base_filtros.filter(
        etapa=Sick.Etapa.AGUARDANDO_RETORNO
    ).count()

    if etapa_filter == 'INATIVOS':
        sicks = sicks.filter(status_final__in=['INATIVO', 'SUCATA'])
    elif etapa_filter in Sick.Etapa.values:
        sicks = sicks.filter(etapa=etapa_filter)

    if situacao_filter == 'pendentes':
        sicks = sicks.filter(
            ativo=True,
        ).exclude(etapa=Sick.Etapa.FINALIZADO)

    elif situacao_filter == 'manutencao':
        sicks = sicks.filter(
            ativo=True,
            etapa__in=[
                Sick.Etapa.EM_TRANSITO,
                Sick.Etapa.RECEBIDO,
                Sick.Etapa.EM_AVALIACAO,
                Sick.Etapa.EM_MANUTENCAO,
                Sick.Etapa.AGUARDANDO_RETORNO,
            ],
        )

    elif situacao_filter == 'inativos':
        sicks = sicks.filter(
            status_final__in=['INATIVO', 'SUCATA']
        )

    elif situacao_filter == 'resolvidos':
        sicks = sicks.filter(
            etapa=Sick.Etapa.FINALIZADO,
            status_final='ATIVO',
        )

    elif situacao_filter == 'abertos':
        sicks = sicks.filter(
            ativo=True
        )

    sicks = sicks.order_by('-data_ocorrencia')

    permissoes_manutencao = [
        'estoque.receber_equipamento_manutencao',
        'estoque.avaliar_equipamento_sick',
        'estoque.iniciar_manutencao_equipamento',
        'estoque.concluir_manutencao_equipamento',
    ]
    usuario_manutencao = (
        pode_realizar_manutencao_sick(request.user) or
        any(request.user.has_perm(permissao) for permissao in permissoes_manutencao)
    )
    bases_usuario_ids = set(perfil.regionais.values_list('pk', flat=True))

    for sick in sicks:
        tem_acesso_base = (
            perfil.is_admin or
            sick.equipamento.regional_id in bases_usuario_ids
        )
        sick.pode_acao_base = (
            perfil.is_admin or
            (
                not usuario_manutencao and tem_acesso_base and
                (perfil.is_gestor or perfil.is_operador)
            )
        )
        sick.pode_acao_manutencao = perfil.is_admin or usuario_manutencao
        sick.pode_enviar_base = (
            not usuario_manutencao and tem_acesso_base and
            (perfil.is_gestor or perfil.is_operador)
        )
        sick.pode_confirmar_recebimento = (
            perfil.is_admin or usuario_manutencao
        )
        sick.historico_completo = sick.equipamento.historico_sick_prefetch
        eventos_por_sick = {}
        for evento in sick.equipamento.eventos_sick_prefetch:
            sick_evento_id = (evento.detalhes or {}).get('sick_id')
            if sick_evento_id is not None:
                eventos_por_sick.setdefault(str(sick_evento_id), []).append(evento)
        for ocorrencia in sick.historico_completo:
            eventos = eventos_por_sick.get(str(ocorrencia.pk), [])

            def evento_etapa(*tipos):
                return next(
                    (evento for evento in eventos if evento.tipo_acao in tipos),
                    None,
                )

            ocorrencia.evento_identificacao = evento_etapa('SICK')
            ocorrencia.evento_envio = evento_etapa('SICK_ENVIO_MANUTENCAO')
            ocorrencia.evento_recebimento = evento_etapa('SICK_RECEBIMENTO_MANUTENCAO')
            ocorrencia.evento_avaliacao = evento_etapa('SICK_AVALIACAO')
            ocorrencia.evento_manutencao = evento_etapa('MANUTENCAO_INICIADA')
            ocorrencia.evento_conclusao = evento_etapa(
                'MANUTENCAO_CONCLUIDA', 'MANUTENCAO_ATUALIZADA'
            )
            ocorrencia.evento_finalizacao = evento_etapa(
                'SICK_RETORNO_CONFIRMADO', 'SICK_INATIVADO', 'RESOLUCAO_SICK'
            )
            ocorrencia.detalhes_identificacao = (
                ocorrencia.evento_identificacao.detalhes
                if ocorrencia.evento_identificacao else {}
            ) or {}
            ocorrencia.detalhes_envio = (
                ocorrencia.evento_envio.detalhes if ocorrencia.evento_envio else {}
            ) or {}
            ocorrencia.detalhes_recebimento = (
                ocorrencia.evento_recebimento.detalhes
                if ocorrencia.evento_recebimento else {}
            ) or {}
            ocorrencia.detalhes_avaliacao = (
                ocorrencia.evento_avaliacao.detalhes
                if ocorrencia.evento_avaliacao else {}
            ) or {}
            ocorrencia.detalhes_manutencao = (
                ocorrencia.evento_manutencao.detalhes
                if ocorrencia.evento_manutencao else {}
            ) or {}
            ocorrencia.detalhes_conclusao = (
                ocorrencia.evento_conclusao.detalhes
                if ocorrencia.evento_conclusao else {}
            ) or {}
            ocorrencia.detalhes_finalizacao = (
                ocorrencia.evento_finalizacao.detalhes
                if ocorrencia.evento_finalizacao else {}
            ) or {}
            ocorrencia.observacao_identificacao_historico = (
                ocorrencia.detalhes_identificacao.get('observacao', '')
            )
            ocorrencia.observacao_envio_historico = (
                ocorrencia.detalhes_envio.get('observacao', '')
            )
            ocorrencia.observacao_recebimento_historico = (
                ocorrencia.detalhes_recebimento.get('observacao', '')
            )
            ocorrencia.observacao_avaliacao_historico = (
                ocorrencia.detalhes_avaliacao.get('observacao', '')
            )
            ocorrencia.observacao_manutencao_historico = (
                ocorrencia.detalhes_manutencao.get('observacao', '')
            )
            ocorrencia.observacao_conclusao_historico = (
                ocorrencia.detalhes_conclusao.get('observacao', '')
            )
            ocorrencia.observacao_finalizacao_historico = (
                ocorrencia.detalhes_finalizacao.get('observacao', '')
            )
        sick.total_ocorrencias = len(sick.historico_completo)
        sick.total_envios_manutencao = sum(
            1 for ocorrencia in sick.historico_completo
            if ocorrencia.enviado_manutencao_em
        )
        sick.reincidente = sick.total_ocorrencias > 1

        sick.ultimo_sick = sick.historico_completo[0] if sick.historico_completo else None
        sick.timeline = [
            {'nome': Sick.Etapa.IDENTIFICADO.label, 'data': sick.data_ocorrencia, 'usuario': None},
            {'nome': Sick.Etapa.EM_TRANSITO.label, 'data': sick.enviado_manutencao_em, 'usuario': sick.enviado_manutencao_por},
            {'nome': Sick.Etapa.RECEBIDO.label, 'data': sick.recebido_manutencao_em, 'usuario': sick.recebido_manutencao_por},
            {'nome': Sick.Etapa.EM_AVALIACAO.label, 'data': sick.avaliacao_iniciada_em, 'usuario': sick.avaliacao_iniciada_por},
            {'nome': Sick.Etapa.EM_MANUTENCAO.label, 'data': sick.manutencao_iniciada_em, 'usuario': sick.manutencao_iniciada_por},
            {'nome': Sick.Etapa.AGUARDANDO_RETORNO.label, 'data': sick.manutencao_concluida_em, 'usuario': sick.manutencao_concluida_por},
            {
                'nome': Sick.Etapa.FINALIZADO.label,
                'data': sick.retorno_confirmado_em or sick.data_resolucao,
                'usuario': sick.retorno_confirmado_por or sick.resolvido_por,
            },
        ]

    categorias = Produto.objects.values_list(
        'categoria',
        flat=True
    ).distinct().order_by('categoria')

    produtos_lista = Produto.objects.filter(
        equipamento__sicks__in=sicks_base_filtros
    ).distinct().order_by('descricao')

    if pode_realizar_manutencao_sick(request.user):
        regionais = Base.objects.all().order_by('nome')
    else:
        regionais = perfil.regionais.all().order_by('nome')

    filtros_abas = request.GET.copy()
    filtros_abas.pop('etapa', None)
    filtros_abas.pop('sick', None)

    context = {

        'sicks': sicks,

        'total_sick': total_sick,
        'total_pendentes': total_pendentes,
        'total_resolvidos': total_resolvidos,
        'total_manutencao': total_manutencao,
        'total_inativos': total_inativos,
        'total_identificados': total_identificados,
        'total_em_transito': total_em_transito,
        'total_recebidos': total_recebidos,
        'total_em_avaliacao': total_em_avaliacao,
        'total_aguardando_retorno': total_aguardando_retorno,
        'status_filter': situacao_filter,
        'situacao_filter': situacao_filter,
        'busca': busca,
        'produto_filter': produto_filter,
        'categoria_filter': categoria_filter,
        'regional_filter': regional_filter,
        'etapa_filter': etapa_filter,
        'filtros_abas': filtros_abas.urlencode(),
        'etapas': Sick.Etapa.choices,
        'usuario_manutencao': usuario_manutencao,
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
            SickService.marcar_como_sick(
                equipamento_id=equipamento.pk,
                usuario=request.user,
                categoria=form.cleaned_data['categoria'],
                motivo=form.cleaned_data['motivo'],
                observacao='Ocorrência registrada pelo formulário de SICK.',
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
        categoria = body.get('categoria', 'OPERACIONAL').strip()
        observacao = body.get('observacao', '').strip()
        senha = body.get('senha', '')
    except json.JSONDecodeError:
        motivo = ''
        categoria = 'OPERACIONAL'
        observacao = ''
        senha = ''

    if not isinstance(senha, str) or not request.user.check_password(senha):
        return JsonResponse({
            'success': False,
            'message': 'Senha incorreta. O equipamento não foi marcado como SICK.',
        }, status=403)

    # Se não veio motivo ou está vazio, usa um valor padrão
    if not motivo:
        motivo = 'Manutenção'

    try:
        sick = SickService.marcar_como_sick(
            equipamento_id=equipamento.pk,
            usuario=request.user,
            categoria=categoria,
            motivo=motivo,
            observacao=observacao,
        )
    except (ValidationError, PermissionDenied) as exc:
        texto = '; '.join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
        return JsonResponse({'success': False, 'message': texto}, status=400)

    return JsonResponse({'sucesso': True, 'sick_id': sick.pk, 'etapa': sick.etapa})

@login_required
def detalhes_sick(request, sick_id):

    sick = get_object_or_404(
        SickService.visiveis_para(request.user, Sick.objects.select_related(
            'equipamento',
            'equipamento__produto',
            'equipamento__regional',
            'resolvido_por'
        )),
        id=sick_id
    )

    historicos = Historico.objects.filter(
        equipamento=sick.equipamento,
        detalhes__sick_id=sick.pk,
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
    protocolo_query = request.GET.get('protocolo', '').strip()
    data_inicio = request.GET.get('data_inicio')
    data_fim = request.GET.get('data_fim')

    historico = (
        Historico.objects
        .select_related(
            'equipamento',
            'equipamento__produto',
            'equipamento__regional',
            'usuario'
        )
        .all()
        .order_by('-data')
    )
    historico = SickService.filtrar_historicos_visiveis(request.user, historico)

    if tipo_acao and tipo_acao != 'todos':
        historico = historico.filter(tipo_acao=tipo_acao)

    if equipamento_query:
        historico = historico.filter(
            Q(equipamento__numero_serie__icontains=equipamento_query) |
            Q(equipamento__patrimonio__icontains=equipamento_query) |
            Q(equipamento__produto__descricao__icontains=equipamento_query)
        )

    if protocolo_query:
        historico = historico.filter(
            detalhes__protocolo__icontains=protocolo_query
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

    paginator = Paginator(historico, 25)
    page_number = request.GET.get('page')
    historicos = paginator.get_page(page_number)

    return render(request, 'estoque/historico.html', {
        'historicos': historicos,
        'total_registros': total_registros,
        'acoes_agrupadas': acoes_agrupadas,
        'tipos_acao': Historico.TIPO_ACOES,
        'filtros': {
            'tipo_acao': tipo_acao or 'todos',
            'equipamento_query': equipamento_query or '',
            'protocolo_query': protocolo_query,
            'data_inicio': data_inicio or '',
            'data_fim': data_fim or '',
        }
    })

@login_required
@role_required('admin', 'gestor')
def historico_detalhes_view(request, historico_id):
    historico = get_object_or_404(
        SickService.filtrar_historicos_visiveis(request.user, Historico.objects.select_related(
            'equipamento',
            'equipamento__produto',
            'equipamento__regional',
            'usuario'
        )),
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
        f"Lista_Equipamentos_{regional_nome}.xlsx"
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
            'finalidade_choices': Equipamento.Finalidade.choices,
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
                codigo_rastreio_envio=request.POST.get('codigo_rastreio_envio'),
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
            codigo_rastreio_devolucao=request.POST.get('codigo_rastreio_devolucao'),
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
        Transferencia.objects
        .select_related('regional_origem', 'regional_destino', 'solicitado_por')
        .prefetch_related(
            'itens__equipamento__produto',
            'itens__pendencias',
            'divergenciatransferencia_set__item',
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
            transferencia.codigo_rastreio = request.POST.get('codigo_rastreio', '').strip()
            transferencia.save(update_fields=['status', 'data_envio', 'codigo_rastreio', 'updated_at'])

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
        equipamento=eq,
        tipo_acao='TRANSFERENCIA',
        usuario=request.user,
        detalhes=detalhes_transferencia(
            transferencia=transferencia,
            equipamento=eq,
            usuario=request.user,
            evento='TRANSFERENCIA_ENVIADA',
            extras={
                'data_transferencia': timezone.now().strftime('%d/%m/%Y %H:%M'),
                'status_anterior_equipamento': 'ATIVO',
                'status_atual_equipamento': 'TRANSFERENCIA',
            }
        )
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
                        'transferencia_id': transferencia.id,
                        'protocolo': transferencia.protocolo,
                    }
                )

            transferencia.status = 'EM_TRANSITO'
            transferencia.data_envio = timezone.now()
            transferencia.codigo_rastreio = request.POST.get('codigo_rastreio', '').strip()
            transferencia.save(update_fields=['status', 'data_envio', 'codigo_rastreio', 'updated_at'])

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
        ocorrencias_transferencia = []

        usuarios = None
        comunicado = None
        observacao_recebimento = request.POST.get('observacao_recebimento', '').strip()

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
                            detalhes=detalhes_transferencia(
                                transferencia=transferencia,
                                equipamento=equipamento,
                                usuario=request.user,
                                evento='TRANSFERENCIA_RECEBIDA',
                                observacao=observacao_recebimento,
                                extras={
                                    'recebido_por': request.user.username,
                                    'status_item': item.status,
                                    'status_anterior_equipamento': 'TRANSFERENCIA',
                                    'status_atual_equipamento': 'ATIVO',
                                }
                            )
                        )

                        total_recebidos += 1

                    elif status_item == 'DIVERGENTE':

                        serie_recebida = request.POST.get(f'serie_recebida_{item.id}', '').strip()
                        patrimonio_recebido = request.POST.get(f'patrimonio_recebido_{item.id}', '').strip()
                        observacao = (
                            request.POST.get(f'observacao_item_{item.id}', '').strip()
                            or observacao_recebimento
                        )

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
                            patrimonio_recebido=patrimonio_recebido,
                            observacao=observacao,
                        )

                        Historico.objects.create(
                            equipamento=equipamento,
                            tipo_acao='TRANSFERENCIA_DIVERGENTE',
                            usuario=request.user,
                            detalhes=detalhes_transferencia(
                                transferencia=transferencia,
                                equipamento=equipamento,
                                usuario=request.user,
                                evento='TRANSFERENCIA_DIVERGENTE',
                                observacao=observacao,
                                extras={
                                    'recebido_por': request.user.username,
                                    'status_item': item.status,
                                    'serie_recebida': serie_recebida,
                                    'patrimonio_recebido': patrimonio_recebido,
                                    'serie_enviada': equipamento.numero_serie,
                                    'patrimonio_enviado': equipamento.patrimonio,
                                }
                            )
                        )

                        divergencia_detectada = True
                        total_divergentes += 1
                        ocorrencias_transferencia.append({
                            "produto": equipamento.produto.descricao if equipamento.produto else "",
                            "serie_enviada": getattr(equipamento, "numero_serie", "") or getattr(equipamento, "serial", ""),
                            "patrimonio_enviado": getattr(equipamento, "patrimonio", ""),
                            "status": item.status,
                            "serie_recebida": serie_recebida,
                            "patrimonio_recebido": patrimonio_recebido,
                            "observacao": observacao,
                        })

                    elif status_item == 'NAO_RECEBIDO':

                        observacao = (
                            request.POST.get(f'observacao_item_{item.id}', '').strip()
                            or observacao_recebimento
                        )

                        equipamento.regional = transferencia.regional_origem
                        equipamento.status = 'ATIVO'
                        equipamento.save(update_fields=['regional', 'status'])

                        item.status = 'NAO_RECEBIDO'
                        item.save(update_fields=['status'])

                        PendenciaTransferencia.objects.create(
                            transferencia=transferencia,
                            item=item,
                            equipamento=equipamento,
                            tipo='NAO_RECEBIDO',
                            motivo='NAO_RECEBIDO',
                            patrimonio_esperado=equipamento.patrimonio or '',
                            serie_esperada=getattr(equipamento, "numero_serie", "") or getattr(equipamento, "serial", ""),
                            descricao=observacao,
                            criado_por=request.user,
                        )

                        Historico.objects.create(
                            equipamento=equipamento,
                            tipo_acao='ITEM_NAO_RECEBIDO',
                            usuario=request.user,
                            detalhes=detalhes_transferencia(
                                transferencia=transferencia,
                                equipamento=equipamento,
                                usuario=request.user,
                                evento='ITEM_NAO_RECEBIDO',
                                observacao=observacao,
                                extras={
                                    'recebido_por': request.user.username,
                                    'status_item': item.status,
                                    'serie_esperada': equipamento.numero_serie,
                                    'patrimonio_esperado': equipamento.patrimonio,
                                }
                            )
                        )

                        pendencia_detectada = True
                        total_nao_recebidos += 1
                        ocorrencias_transferencia.append({
                            "produto": equipamento.produto.descricao if equipamento.produto else "",
                            "serie_enviada": getattr(equipamento, "numero_serie", "") or getattr(equipamento, "serial", ""),
                            "patrimonio_enviado": getattr(equipamento, "patrimonio", ""),
                            "status": item.status,
                            "serie_recebida": "",
                            "patrimonio_recebido": "",
                            "observacao": observacao,
                        })

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

            if observacao_recebimento:
                conteudo += f"\nObservaÃ§Ãµes gerais: {observacao_recebimento}\n"

            itens_detalhados = ocorrencias_transferencia

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
            Transferencia.objects.select_related('regional_origem__empresa', 'regional_destino'),
            request.user,
            'regional_origem__empresa'
        ),
        id=transferencia_id
    )

    if transferencia.status != 'PENDENTE':
        messages.error(request, "Apenas pendentes.")
        return redirect('estoque:lista_transferencias')

    from estoque.services.transferencia_services import cancelar_transferencia as cancelar
    cancelar(transferencia, request.user)

    messages.success(request, "Cancelada com sucesso.")
    return redirect('estoque:lista_transferencias')

@login_required
@role_required('admin', 'gestor')
def lista_transferencias(request):

    perfil = request.user.perfil
    busca = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()

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

    if busca:
        base_qs = base_qs.filter(
            Q(protocolo__icontains=busca) |
            Q(regional_origem__nome__icontains=busca) |
            Q(regional_destino__nome__icontains=busca) |
            Q(solicitado_por__username__icontains=busca) |
            Q(itens__equipamento__numero_serie__icontains=busca) |
            Q(itens__equipamento__patrimonio__icontains=busca) |
            Q(itens__equipamento__produto__descricao__icontains=busca)
        ).distinct()

    if status:
        base_qs = base_qs.filter(status=status)

    transferencias = list(base_qs)

    hoje = timezone.now().date()

    total_pendentes = sum(t.status == 'PENDENTE' for t in transferencias)
    total_em_transito = sum(t.status == 'EM_TRANSITO' for t in transferencias)
    total_concluidas = sum(t.status == 'CONCLUIDA' for t in transferencias)
    total_canceladas = sum(t.status == 'CANCELADA' for t in transferencias)

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
        'filtros': {
            'q': busca,
            'status': status,
        },
    })

@login_required
@role_required('admin', 'gestor')
def equipamentos_por_regional(request, produto_id, regional_id):
    perfil = request.user.perfil

    if not perfil.is_admin and not perfil.regionais.filter(id=regional_id).exists():
        return JsonResponse({'erro': 'Acesso negado a esta regional'}, status=403)

    if _base_em_auditoria(regional_id):
        return _resposta_base_em_auditoria()

    sicks_visiveis = SickService.visiveis_para(
        request.user,
        Sick.objects.order_by('-data_ocorrencia'),
    )
    equipamentos = Equipamento.objects.filter(
        produto_id=produto_id,
        regional_id=regional_id
    ).select_related('produto', 'regional__empresa').prefetch_related(
        Prefetch('sicks', queryset=sicks_visiveis, to_attr='sicks_ordenados')
    )

    data = {
        'equipamentos': [
            {
                'id': e.id,
                'numero_serie': e.numero_serie,
                'patrimonio': e.patrimonio,
                'status': e.status,
                'status_label': e.get_status_display(),
                'finalidade': e.finalidade,
                'finalidade_label': e.get_finalidade_display(),
                'empresa': e.regional.empresa.nome,
                'base': e.regional.nome,
                'categoria': e.produto.categoria if e.produto else '',
                'produto': e.produto.descricao if e.produto else '',
                'fabricante': e.produto.fabricante if e.produto else '',
                'modelo': e.produto.modelo if e.produto else '',
                'responsavel': e.responsavel,
                'sick': (
                    {
                        'etapa': e.sicks_ordenados[0].etapa,
                        'etapa_label': e.sicks_ordenados[0].get_etapa_display(),
                        'data_ocorrencia': e.sicks_ordenados[0].data_ocorrencia.isoformat(),
                        'enviado_em': e.sicks_ordenados[0].enviado_manutencao_em.isoformat() if e.sicks_ordenados[0].enviado_manutencao_em else None,
                        'recebido_em': e.sicks_ordenados[0].recebido_manutencao_em.isoformat() if e.sicks_ordenados[0].recebido_manutencao_em else None,
                    }
                    if e.sicks_ordenados else None
                ),
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
        secure_queryset(
            Equipamento.objects.select_related('produto', 'regional__empresa'),
            request.user,
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
                'finalidade_choices': Equipamento.Finalidade.choices,
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

    finalidade = request.POST.get('finalidade', '').strip()

    if finalidade not in Equipamento.Finalidade.values:
        messages.error(
            request,
            'Selecione uma finalidade válida para o equipamento.'
        )
        return redirect(
            request.META.get('HTTP_REFERER', '/')
        )

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
                'finalidade': equipamento.finalidade,
                'foto': (
                    str(equipamento.foto)
                    if equipamento.foto else None
                ),
            }

            alteracoes = {}

            if finalidade and finalidade in Equipamento.Finalidade.values and finalidade != equipamento.finalidade:
                alteracoes['finalidade'] = {
                    'antes': equipamento.finalidade,
                    'depois': finalidade,
                }
                equipamento.finalidade = finalidade

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

                    if equipamento.sicks.filter(ativo=True).exclude(
                        etapa=Sick.Etapa.FINALIZADO
                    ).exists():
                        raise ValidationError(
                            'O status de um equipamento em SICK deve ser alterado pelo fluxo de etapas.'
                        )

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
                        'finalidade': equipamento.finalidade,
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

def detalhes_transferencia(transferencia, equipamento=None, usuario=None, evento=None, observacao=None, extras=None):
    detalhes = {
        'evento': evento,
        'transferencia_id': transferencia.id,
        'protocolo': transferencia.protocolo,

        'solicitado_por': (
            transferencia.solicitado_por.username
            if getattr(transferencia, 'solicitado_por', None)
            else None
        ),

        'transmitido_por': (
            usuario.username
            if usuario
            else None
        ),

        'data_envio': (
            transferencia.data_envio.strftime('%d/%m/%Y %H:%M')
            if transferencia.data_envio
            else None
        ),

        'data_recebimento': (
            transferencia.data_recebimento.strftime('%d/%m/%Y %H:%M')
            if transferencia.data_recebimento
            else None
        ),

        'regional_origem': (
            transferencia.regional_origem.nome
            if transferencia.regional_origem
            else None
        ),

        'regional_destino': (
            transferencia.regional_destino.nome
            if transferencia.regional_destino
            else None
        ),

        'status_transferencia': transferencia.status,

        'produto': (
            equipamento.produto.descricao
            if equipamento and equipamento.produto
            else None
        ),

        'numero_serie': (
            equipamento.numero_serie
            if equipamento
            else None
        ),

        'patrimonio': (
            equipamento.patrimonio
            if equipamento
            else None
        ),

        'status_equipamento': (
            equipamento.status
            if equipamento
            else None
        ),

        'observacao': observacao,
    }

    if extras:
        detalhes.update(extras)

    return detalhes

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
            perfil = request.user.perfil
            if not perfil.is_admin:
                regionais_ids = perfil.bases_checklist_ids
                if (
                    inventario.base_id not in regionais_ids or
                    inventario.base.empresa_id != perfil.empresa_id
                ):
                    messages.error(request, 'Você não tem acesso à base deste inventário.')
                    return redirect('estoque:checklist')

            lider_atual = (inventario.lider or '').strip()
            lider_informado = request.POST.get('lider', '').strip()
            lider_editavel = (
                not lider_atual or
                lider_atual.lower() in ('a definir', 'a-definir')
            )

            # Captura equipamentos selecionados
            categorias_equipamentos = ['router', 'coletor', 'notebook', 'impressora']
            equipamentos_ids = []
            for categoria in categorias_equipamentos:
                equipamentos_ids.extend(request.POST.getlist(f'equipamentos_{categoria}'))

            if inventario.pessoas is not None:
                limite_coletores = inventario.pessoas + 5
                total_coletores = (
                    Equipamento.objects
                    .filter(
                        id__in=equipamentos_ids,
                        regional_id=inventario.base_id,
                        produto__categoria='Coletores',
                    )
                    .count()
                )
                if total_coletores > limite_coletores:
                    raise ValidationError(
                        f'Este inventário permite no máximo {limite_coletores} '
                        f'coletores ({inventario.pessoas} pessoas + 5 de backup).'
                    )

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
                modo_rolo = request.POST.get(f'tag_modo_rolo_{rolo_id}', 'REUTILIZACAO')
                if numero_inicial:
                    tags_payload.append((rolo_id, numero_inicial, modo_rolo))

            if not equipamentos_ids and not insumos_payload and not tags_payload:
                messages.error(request, 'Selecione ao menos um equipamento, informe um insumo ou adicione um lote de TAG.')
                return redirect('estoque:checklist')

            campos_declaracao = {
                'departamento_pessoal': 'declaracao_departamento_pessoal',
                'fios_cabos': 'declaracao_fios_cabos',
                'coletor_dados': 'declaracao_coletor_dados',
                'impressora': 'declaracao_impressora',
                'escada': 'declaracao_escada',
                'balanca': 'declaracao_balanca',
                'extensor_rede_carrinho': 'declaracao_extensor_rede_carrinho',
            }
            declaracao_quantidades = {}
            if any(nome in request.POST for nome in campos_declaracao.values()):
                for chave, nome_post in campos_declaracao.items():
                    try:
                        quantidade = int(request.POST.get(nome_post, '0') or '0')
                    except (TypeError, ValueError) as exc:
                        raise ValidationError(
                            'As quantidades da declaração devem ser números inteiros.'
                        ) from exc
                    if quantidade < 0:
                        raise ValidationError(
                            'As quantidades da declaração não podem ser negativas.'
                        )
                    declaracao_quantidades[chave] = quantidade
            try:
                quantidade_volumes = int(
                    request.POST.get('quantidade_volumes', '0')
                )
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    'Informe uma quantidade de volumes válida para a declaração.'
                ) from exc
            if quantidade_volumes <= 0 or quantidade_volumes > 9999:
                raise ValidationError(
                    'Informe uma quantidade de volumes entre 1 e 9999.'
                )
            transporte = request.POST.get('transporte', '').strip()

            def ler_horario_declaracao(nome):
                valor = request.POST.get(nome, '').strip()
                if not valor:
                    return None
                try:
                    return datetime.strptime(valor, '%H:%M').time()
                except ValueError as exc:
                    raise ValidationError(
                        f'Informe um horário válido para {nome.replace("_", " ")}.'
                    ) from exc

            ponto_encontro = request.POST.get('ponto_encontro', '').strip()
            horario_ponto = ler_horario_declaracao('horario_ponto')
            horario_inicio = ler_horario_declaracao('horario_inicio')
            declaracao_dados = {
                'cliente': request.POST.get(
                    'declaracao_cliente', inventario.cliente.sigla
                ).strip(),
                'loja': request.POST.get(
                    'declaracao_loja', str(inventario.loja)
                ).strip(),
                'data': request.POST.get(
                    'declaracao_data', inventario.data_inicio.strftime('%d/%m/%Y')
                ).strip(),
                'endereco': request.POST.get(
                    'declaracao_endereco', inventario.endereco or ''
                ).strip(),
                'bairro': request.POST.get(
                    'declaracao_bairro', inventario.bairro or ''
                ).strip(),
                'cidade': request.POST.get(
                    'declaracao_cidade', inventario.cidade or ''
                ).strip(),
                'horario_entrega': request.POST.get('horario_ponto', '').strip(),
                'horario_inicio': request.POST.get('horario_inicio', '').strip(),
                'ponto_encontro': ponto_encontro,
                'transporte': transporte,
            }

            with transaction.atomic():
                campos_inventario = []
                if lider_informado and lider_editavel:
                    inventario.lider = lider_informado
                    campos_inventario.append('lider')

                inventario.ponto_encontro = ponto_encontro
                inventario.horario_ponto = horario_ponto
                inventario.horario_inicio = horario_inicio
                campos_inventario.extend([
                    'ponto_encontro',
                    'horario_ponto',
                    'horario_inicio',
                ])
                inventario.save(update_fields=campos_inventario)

                checklist = ChecklistService.criar(
                    inventario=inventario,
                    usuario=request.user,
                    observacao=request.POST.get('observacao', ''),
                    quantidade_volumes=quantidade_volumes,
                    transporte=transporte,
                    declaracao_quantidades=declaracao_quantidades,
                    declaracao_dados=declaracao_dados,
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

                        if not insumo:
                            continue

                        if (
                            insumo.categoria and
                            insumo.categoria.nome.upper() == "TAGS" and
                            request.POST.get(f'insumo_{insumo_id}_modo_tag') == 'REUTILIZACAO'
                        ):
                            ItemChecklist.objects.get_or_create(
                                checklist=checklist,
                                insumo=insumo,
                                defaults={
                                    'quantidade_enviada': quantidade,
                                    'quantidade_utilizada': quantidade,
                                    'quantidade_retornada': 0,
                                    'quantidade_perdida': 0,
                                    'status_retorno': 'CONFERIDO',
                                },
                            )
                        else:
                            ChecklistService.registrar_envio_item(
                                checklist=checklist,
                                insumo=insumo,
                                quantidade_enviada=quantidade,
                                usuario=request.user,
                            )

                if tags_payload:
                    rolos_ids = [item[0] for item in tags_payload]
                    rolos_dict = {
                        str(rolo.id): rolo
                        for rolo in RoloTag.objects.select_related('lote').filter(id__in=rolos_ids)
                    }
                    for rolo_id, numero_inicial, modo_rolo in tags_payload:
                        rolo = rolos_dict.get(rolo_id)
                        if rolo:
                            ChecklistService.adicionar_lote_tag(
                                checklist=checklist,
                                lote=rolo.lote,
                                rolo=rolo,
                                numero_inicial_utilizado=numero_inicial,
                                modo_rolo=modo_rolo,
                                usuario=request.user
                            )

                checklist.status = 'EM_EXECUCAO'
                checklist.save(update_fields=['status'])

                if inventario.status == 'PLANEJADO':
                    inventario.status = 'EM_ANDAMENTO'
                    inventario.save(update_fields=['status'])

                ComunicadoService.checklist_criado(checklist, request.user)

            messages.success(request, 'Checklist criado e estoque movimentado com sucesso!')
            return redirect('insumos:imprimir_checklist', pk=checklist.pk)

        except Exception as e:
            messages.error(request, f'Erro ao criar checklist: {str(e)}')
            return redirect('estoque:checklist')

    # --- GET: Exibir formulário ---
    perfil = request.user.perfil
    bases_checklist = perfil.bases_checklist_ativas
    regionais_ids = perfil.bases_checklist_ids

    if perfil.is_admin:
        equipamentos = Equipamento.objects.filter(
            status='ATIVO', finalidade=Equipamento.Finalidade.OPERACIONAL
        )
        inventarios = Inventario.objects.filter(
            status='PLANEJADO',
            data_inicio=date.today()
        )
        lotes_tags = RoloTag.objects.filter(status__in=['DISPONIVEL', 'EM_USO'], lote__ativo=True).select_related('lote', 'lote__base')
    else:
        equipamentos = Equipamento.objects.filter(
            status='ATIVO',
            finalidade=Equipamento.Finalidade.OPERACIONAL,
            regional_id__in=regionais_ids
        )
        inventarios = Inventario.objects.filter(
            status='PLANEJADO',
            base__in=bases_checklist,
            base__empresa=perfil.empresa,
            data_inicio=date.today()
        )
        lotes_tags = RoloTag.objects.filter(
            status__in=['DISPONIVEL', 'EM_USO'],
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
        {"id": 10, "descricao": "Etiqueta Setor 00001", "grupo": "TAGS", "tag": True},
        {"id": 11, "descricao": "Etiqueta Setor 01000", "grupo": "TAGS", "tag": True},
        {"id": 12, "descricao": "Etiqueta Setor 02000", "grupo": "TAGS", "tag": True},
        {"id": 13, "descricao": "Etiqueta Setor 03000", "grupo": "TAGS", "tag": True},
        {"id": 14, "descricao": "Etiqueta Setor 03500 - Peso Variável", "grupo": "TAGS", "tag": True},
        {"id": 15, "descricao": "Etiqueta Setor 04000", "grupo": "TAGS", "tag": True},
        {"id": 16, "descricao": "Etiqueta Setor 05000", "grupo": "TAGS", "tag": True},
        {"id": 17, "descricao": "Etiqueta Setor 06000", "grupo": "TAGS", "tag": True},
        {"id": 18, "descricao": "Etiqueta Setor 07000", "grupo": "TAGS", "tag": True},
        {"id": 19, "descricao": "Etiqueta Setor 08000", "grupo": "TAGS", "tag": True},
        {"id": 20, "descricao": "Etiqueta Setor 09000", "grupo": "TAGS", "tag": True},
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

@login_required
def get_equipamentos_disponiveis(request):
    regional_id = request.GET.get('regional')
    categoria = request.GET.get('categoria')

    if not regional_id or not categoria:
        return JsonResponse({'results': []})

    if str(regional_id).isdigit() and _base_em_auditoria(regional_id):
        return _resposta_base_em_auditoria()

    if not request.user.perfil.is_admin:
        regionais_ids = request.user.perfil.bases_checklist_ids
        if int(regional_id) not in regionais_ids:
            return JsonResponse({'results': []}, status=403)

    equipamentos = Equipamento.objects.filter(
        status='ATIVO',
        finalidade=Equipamento.Finalidade.OPERACIONAL,
        regional_id=regional_id,
        produto__categoria=categoria,
    ).select_related('produto')

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
        regionais_ids = request.user.perfil.bases_checklist_ids
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

