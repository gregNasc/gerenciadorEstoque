from django.contrib.auth.models import Group
from django.db.models import Q

from estoque.models import Base, CapacidadeRelacionamentoEmpresa, Empresa, Produto
from estoque.security import secure_base_queryset, secure_company_queryset
from insumos.constants import GruposInsumos


class GruposCorporativos:
    COMPRAS_RESTRITO = 'COMPRAS_RESTRITO_NOVAS_FUNCIONALIDADES'
    SICK_GERENCIAR = 'SICK_GERENCIAR'
    SICK_MANUTENCAO = 'SICK_MANUTENCAO'
    COMUNICADOS_EDITOR = 'COMUNICADOS_EDITOR'


class ComprasAccessPolicy:
    COMPRAS = CapacidadeRelacionamentoEmpresa.Recurso.COMPRAS
    CATALOGO = CapacidadeRelacionamentoEmpresa.Recurso.CATALOGO
    ORDENS_SERVICO = CapacidadeRelacionamentoEmpresa.Recurso.ORDENS_SERVICO
    VIEW = CapacidadeRelacionamentoEmpresa.Acao.VISUALIZAR
    CREATE = CapacidadeRelacionamentoEmpresa.Acao.CRIAR
    EDIT = CapacidadeRelacionamentoEmpresa.Acao.EDITAR
    APPROVE = CapacidadeRelacionamentoEmpresa.Acao.APROVAR
    EXPORT = CapacidadeRelacionamentoEmpresa.Acao.EXPORTAR
    ADMIN = CapacidadeRelacionamentoEmpresa.Acao.ADMINISTRAR

    PERMISSOES_OPERACIONAIS = (
        'insumos.visualizar_valores_estoque',
        'insumos.gerenciar_precos',
        'insumos.gerenciar_fornecedores',
        'insumos.criar_remessa_compra',
        'estoque.visualizar_preco_produto',
        'estoque.definir_preco_produto',
        'estoque.alterar_preco_produto',
        'estoque.importar_preco_produto',
        'estoque.cadastrar_equipamentos',
    )

    @staticmethod
    def _autenticado(user):
        return bool(user and user.is_authenticated)

    @classmethod
    def _pertence_ao_grupo(cls, user, nome):
        if not cls._autenticado(user):
            return False
        cache = getattr(user, '_compras_grupos_cache', None)
        if cache is None:
            cache = {}
            user._compras_grupos_cache = cache
        if nome not in cache:
            cache[nome] = user.groups.filter(name=nome).exists()
        return cache[nome]

    @classmethod
    def restrito(cls, user):
        return bool(
            cls._autenticado(user)
            and (
                user.get_username().strip().lower() == 'jose.barboza'
                or cls._pertence_ao_grupo(user, GruposCorporativos.COMPRAS_RESTRITO)
            )
        )

    @classmethod
    def _admin_ou_compras(cls, user):
        if not cls._autenticado(user) or cls.restrito(user):
            return False
        perfil = getattr(user, 'perfil', None)
        return bool(
            user.is_superuser
            or (perfil and perfil.is_admin)
            or cls._pertence_ao_grupo(user, GruposInsumos.COMPRAS)
        )

    @classmethod
    def pode_visualizar_valores(cls, user):
        if cls.restrito(user):
            return False
        perfil = getattr(user, 'perfil', None)
        return bool(
            cls._admin_ou_compras(user)
            or user.has_perm('insumos.visualizar_valores_estoque')
            or user.has_perm('estoque.visualizar_preco_produto')
            or (
                perfil
                and (perfil.is_financeiro_insumos or perfil.is_executivo_insumos)
            )
        )

    @classmethod
    def pode_editar_precos(cls, user):
        return cls._admin_ou_compras(user) or (
            cls._autenticado(user)
            and not cls.restrito(user)
            and user.has_perm('insumos.gerenciar_precos')
        ) or (
            cls._autenticado(user)
            and not cls.restrito(user)
            and (
                user.has_perm('estoque.definir_preco_produto')
                or user.has_perm('estoque.alterar_preco_produto')
                or user.has_perm('estoque.importar_preco_produto')
            )
        )

    @classmethod
    def pode_definir_preco_produto(cls, user):
        return bool(
            cls._admin_ou_compras(user)
            or (
                cls._autenticado(user)
                and not cls.restrito(user)
                and (
                    user.has_perm('insumos.gerenciar_precos')
                    or user.has_perm('estoque.definir_preco_produto')
                )
            )
        )

    @classmethod
    def _possui_escopo_delegado(cls, user):
        return bool(
            cls._autenticado(user)
            and not cls.restrito(user)
            and any(user.has_perm(permissao) for permissao in cls.PERMISSOES_OPERACIONAIS)
        )

    @classmethod
    def pode_alterar_preco_produto(cls, user):
        return bool(
            cls._admin_ou_compras(user)
            or (
                cls._autenticado(user)
                and not cls.restrito(user)
                and (
                    user.has_perm('insumos.gerenciar_precos')
                    or user.has_perm('estoque.alterar_preco_produto')
                )
            )
        )

    @classmethod
    def pode_importar_precos(cls, user):
        return bool(
            cls._admin_ou_compras(user)
            or (
                cls._autenticado(user)
                and not cls.restrito(user)
                and (
                    user.has_perm('insumos.gerenciar_precos')
                    or user.has_perm('estoque.importar_preco_produto')
                )
            )
        )

    @classmethod
    def pode_gerenciar_catalogo(cls, user):
        return cls._admin_ou_compras(user) or (
            cls._autenticado(user)
            and not cls.restrito(user)
            and user.has_perm('estoque.cadastrar_equipamentos')
        )

    @classmethod
    def pode_gerenciar_fornecedores(cls, user):
        # FornecedorInsumo é o diretório jurídico global da plataforma.
        # Condições e preços operacionais são tenant-specific; o cadastro
        # canônico só pode ser alterado pelo Superuser.
        return bool(cls._autenticado(user) and user.is_superuser)

    @classmethod
    def pode_criar_remessa(cls, user):
        return cls._admin_ou_compras(user) or (
            cls._autenticado(user)
            and not cls.restrito(user)
            and user.has_perm('insumos.criar_remessa_compra')
        )

    @classmethod
    def empresas(cls, user, *, action=VIEW, resource=COMPRAS):
        if not (cls._admin_ou_compras(user) or cls._possui_escopo_delegado(user)):
            return Empresa.objects.none()
        if user.is_superuser:
            return Empresa.objects.all()
        perfil = getattr(user, 'perfil', None)
        if not perfil:
            return Empresa.objects.none()
        if perfil.is_admin:
            return secure_company_queryset(
                Empresa.objects.all(),
                user,
                resource=resource,
                action=action,
            )
        ids = list(perfil.empresas_escopo_compras.values_list('pk', flat=True))
        if perfil.empresa_id:
            ids.append(perfil.empresa_id)
        return Empresa.objects.filter(pk__in=set(ids))

    @classmethod
    def bases(cls, user, *, action=VIEW, resource=COMPRAS):
        if not (cls._admin_ou_compras(user) or cls._possui_escopo_delegado(user)):
            return Base.objects.none()
        if user.is_superuser:
            return Base.objects.all()
        perfil = getattr(user, 'perfil', None)
        if not perfil:
            return Base.objects.none()
        if perfil.is_admin:
            return secure_base_queryset(
                Base.objects.all(),
                user,
                resource=resource,
                action=action,
            )
        ids = set(perfil.bases_escopo_compras.values_list('pk', flat=True))
        ids.update(perfil.regionais.values_list('pk', flat=True))
        return Base.objects.filter(
            pk__in=ids,
            empresa__in=cls.empresas(user, action=action, resource=resource),
        )

    @classmethod
    def produtos_catalogo(cls, user, *, empresa=None, action=VIEW):
        """Produtos habilitados nas empresas acessíveis ao usuário.

        Empresas ainda não configuradas preservam o catálogo global legado até
        que o Admin salve sua primeira seleção explícita.
        """
        from compras.models import CatalogoProdutoEmpresa

        empresas = cls.empresas(user, action=action, resource=cls.CATALOGO)
        if empresa is not None:
            empresas = empresas.filter(pk=getattr(empresa, 'pk', empresa))
        empresas_ids = list(empresas.values_list('pk', flat=True))
        if not empresas_ids:
            return Produto.objects.none()

        configuradas = set(
            CatalogoProdutoEmpresa.objects.filter(
                empresa_id__in=empresas_ids
            ).values_list('empresa_id', flat=True)
        )
        sem_configuracao = set(empresas_ids) - configuradas
        produtos_ids = CatalogoProdutoEmpresa.objects.filter(
            empresa_id__in=configuradas,
            ativo=True,
        ).values('produto_id')
        filtro = Q(pk__in=produtos_ids)
        if sem_configuracao:
            filtro |= Q(ativo=True)
        return Produto.objects.filter(filtro, ativo=True).distinct()

    @classmethod
    def admins_para_empresa(cls, empresa, *, action=VIEW, resource=COMPRAS):
        from django.contrib.auth.models import User

        candidatos = User.objects.filter(is_active=True).filter(
            Q(is_superuser=True) | Q(perfil__role='admin')
        ).distinct()
        ids = [
            candidato.pk
            for candidato in candidatos
            if cls.empresas(
                candidato,
                action=action,
                resource=resource,
            ).filter(pk=empresa.pk).exists()
        ]
        return User.objects.filter(pk__in=ids, is_active=True)
