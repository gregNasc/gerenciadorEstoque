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
        'caixa_comunicados',
        'detalhe_comunicado',
        'baixar_arquivo_comunicado',
        'ocultar_comunicado',
        'preferencias_whatsapp',
        'logout',
    }
    USUARIOS_COM_OS = {'rafael.ribeiro', 'jose.barboza'}

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
