from .models import Perfil
from django.db import DatabaseError
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.utils import translation

from estoque.policies.compras import GruposCorporativos
from estoque.tenant_context import TenantRequestContext
from estoque.tenant_feature_routes import TenantFeatureRoutePolicy
from estoque.tenant_features import TenantFeatureService
from estoque.services.documentation_section_service import DocumentationSectionService
from estoque.tenant_scope import TenantScope

class EmpresaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        is_authenticated = bool(user and user.is_authenticated)
        context = TenantRequestContext.empty(
            user_id=user.pk if is_authenticated else None,
            is_platform_superuser=bool(is_authenticated and user.is_superuser)
        )

        if is_authenticated:
            try:
                perfil = (
                    Perfil.objects
                    .select_related('empresa')
                    .prefetch_related('empresas_acesso_adicional')
                    .filter(user=user)
                    .first()
                )

                if perfil:
                    context = TenantRequestContext.from_profile(user, perfil)

            except DatabaseError:
                # Falha fechada: ausencia de contexto nunca amplia o escopo.
                context = TenantRequestContext.empty(
                    user_id=user.pk,
                    is_platform_superuser=bool(user.is_superuser)
                )

        request.tenant_context = context
        request.tenant_scope = TenantScope.for_user(user, context=context)
        request.tenant = request.tenant_scope.primary_company

        return self.get_response(request)


class TenantFeatureMiddleware:
    """Bloqueia no backend módulos desabilitados para o tenant da requisição."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated or user.is_superuser:
            return None
        features = TenantFeatureRoutePolicy.required_features(
            request.resolver_match,
            view_kwargs,
        )
        if not features:
            return None
        tenant = getattr(request, 'tenant', None)
        for feature in features:
            if not TenantFeatureService.user_has_feature(
                user,
                feature,
                tenant=tenant,
            ):
                raise PermissionDenied(
                    'Este módulo não está habilitado para sua empresa.'
                )
        section = TenantFeatureRoutePolicy.required_documentation_section(
            request.resolver_match
        )
        if section and not DocumentationSectionService.is_enabled(
            user, section, tenant=tenant
        ):
            raise PermissionDenied(
                'Esta seção de documentação não está habilitada para sua empresa.'
            )
        return None


class TenantMembershipMiddleware:
    """Nega toda a aplicação a usuários sem tenant ativo, salvo logout."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated or user.is_superuser:
            return None
        match = request.resolver_match
        if match and match.url_name == 'logout':
            return None
        tenant = getattr(request, 'tenant', None)
        if tenant is not None and tenant.ativa:
            return None
        raise PermissionDenied(
            'Seu usuário não possui uma empresa ativa. Contate o administrador da plataforma.'
        )

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
        'drivers_impressoras',
        'driver_impressora_arquivo',
        'documentacao',
        'documentacao_legado_arquivo',
        'documentacao_resolucao',
        'documentacao_resolucao_arquivo',
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
        ('estoque', 'documentacao_resolucao_desativar'): 'estoque.gerenciar_documentacao',
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
