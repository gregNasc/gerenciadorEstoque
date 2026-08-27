from .models import Perfil
from django.db import DatabaseError
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.utils import translation

from estoque.policies.compras import GruposCorporativos

class EmpresaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.empresa = None

        user = getattr(request, 'user', None)

        if user and user.is_authenticated:
            try:
                perfil = (
                    Perfil.objects
                    .select_related('empresa')
                    .filter(user=user)
                    .first()
                )

                if perfil:
                    request.empresa = perfil.empresa

            except DatabaseError:
                request.empresa = None

        return self.get_response(request)

class UserLanguageMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        if request.user.is_authenticated:

            perfil = getattr(request.user, 'perfil', None)

            if perfil and perfil.idioma:

                translation.activate(perfil.idioma)
                request.LANGUAGE_CODE = perfil.idioma

        response = self.get_response(request)

        translation.deactivate()

        return response


class OperatorScopeMiddleware:
    """Impede acesso direto de operadores a telas fora do escopo operacional."""

    ROTAS_ESTOQUE_PERMITIDAS = {
        'manuais',
        'documentacao',
        'documentacao_resolucao',
        'documentacao_clientes',
        'documentacao_cliente_detalhe',
        'documentacao_cliente_arquivo',
        'documentacao_videos',
        'caixa_comunicados',
        'detalhe_comunicado',
        'baixar_arquivo_comunicado',
        'ocultar_comunicado',
        'preferencias_whatsapp',
        'logout',
    }
    USUARIOS_COM_OS = {'rafael.ribeiro', 'jose.barboza'}
    PERMISSOES_POR_ROTA = {
        ('compras', 'criar_produto_catalogo'): 'estoque.cadastrar_equipamentos',
        ('compras', 'valores_equipamentos'): 'estoque.visualizar_preco_produto',
        ('compras', 'template_precificacao_equipamentos'): 'estoque.importar_preco_produto',
        ('compras', 'importar_precificacao_equipamentos'): 'estoque.importar_preco_produto',
        ('compras', 'alterar_preco_produto'): (
            'estoque.definir_preco_produto', 'estoque.alterar_preco_produto',
        ),
        ('estoque', 'checklist'): 'insumos.preencher_checklists',
        ('estoque', 'documentacao_video_desativar'): 'estoque.gerenciar_documentacao',
        ('insumos', 'lista_checklists'): 'insumos.visualizar_checklists',
        ('insumos', 'checklist_detail'): 'insumos.visualizar_checklists',
        ('insumos', 'finalizar_checklist'): 'insumos.finalizar_checklists',
        ('insumos', 'reabrir_checklist'): 'insumos.reabrir_checklists',
        ('insumos', 'imprimir_checklist'): 'insumos.imprimir_checklists',
        ('insumos', 'exportar_checklist_modelo'): 'insumos.imprimir_checklists',
        ('insumos', 'editar_itens_checklist'): 'insumos.preencher_checklists',
        ('insumos', 'editar_checklist'): 'insumos.preencher_checklists',
        ('insumos', 'api_ultimo_checklist'): 'insumos.preencher_checklists',
        ('insumos', 'api_insumos_por_base'): 'insumos.preencher_checklists',
        ('insumos', 'inventario_detalhes'): 'insumos.preencher_checklists',
        ('integracao', 'planning_mappings'): 'integracao.gerenciar_mapeamentos_planning',
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return None
        perfil = getattr(user, 'perfil', None)
        if user.is_superuser or not perfil or not perfil.is_operador or perfil.is_funcional_global:
            return None

        match = request.resolver_match
        namespace = match.namespace if match else ''
        url_name = match.url_name if match else ''
        username = user.get_username().strip().lower()

        permissao_view = getattr(view_func, 'required_operational_permission', None)
        permissao_rota = self.PERMISSOES_POR_ROTA.get((namespace, url_name))
        permissoes_rota = (
            permissao_rota if isinstance(permissao_rota, (tuple, list, set))
            else (permissao_rota,) if permissao_rota else ()
        )
        if (
            (permissao_view and user.has_perm(permissao_view))
            or any(user.has_perm(permissao) for permissao in permissoes_rota)
        ):
            return None

        if namespace == 'chamados':
            return None
        if (
            namespace == 'estoque'
            and url_name == 'sick'
            and user.groups.filter(name__in=[
                GruposCorporativos.SICK_GERENCIAR,
                GruposCorporativos.SICK_MANUTENCAO,
            ]).exists()
        ):
            return None
        if namespace == 'ordens_servico' and username in self.USUARIOS_COM_OS:
            return None
        if namespace == 'estoque' and url_name == 'index':
            return redirect('chamados:lista')
        if namespace == 'estoque' and url_name in self.ROTAS_ESTOQUE_PERMITIDAS:
            return None
        if url_name in {'logout', 'health_live', 'health_ready'}:
            return None

        raise PermissionDenied(
            'USUARIOS OPERADORES PODEM ACESSAR APENAS MANUAIS, CHAMADOS E COMUNICADOS.'
        )
