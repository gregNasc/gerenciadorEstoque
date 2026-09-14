from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from estoque.models import Empresa, Modulo, ModuloEmpresa


class TenantFeatureService:
    """API central para configuração e consulta de módulos por tenant.

    A ausência de configuração nunca equivale a módulo habilitado. Empresas
    existentes são populadas pela migration e empresas novas são provisionadas
    pelo signal de criação para preservar o comportamento anterior.
    """

    @classmethod
    def ensure_catalog(cls, *, using='default'):
        created = 0
        for order, (code, name) in enumerate(Modulo.Codigo.choices, start=1):
            _, was_created = Modulo.objects.using(using).get_or_create(
                codigo=code,
                defaults={
                    'nome': name,
                    'ordem': order,
                    'ativo': True,
                },
            )
            created += int(was_created)
        return created

    @staticmethod
    def _tenant_id(tenant):
        if not isinstance(tenant, Empresa) or not tenant.pk:
            return None
        return tenant.pk

    @classmethod
    def has_feature(cls, tenant, codigo):
        tenant_id = cls._tenant_id(tenant)
        codigo = str(codigo or '').strip().lower()
        if not tenant_id or not tenant.ativa or not codigo:
            return False
        return ModuloEmpresa.objects.filter(
            empresa_id=tenant_id,
            modulo__codigo=codigo,
            modulo__ativo=True,
            habilitado=True,
        ).exists()

    @classmethod
    def enabled_features(cls, tenant):
        tenant_id = cls._tenant_id(tenant)
        if not tenant_id or not tenant.ativa:
            return frozenset()
        return frozenset(
            ModuloEmpresa.objects.filter(
                empresa_id=tenant_id,
                modulo__ativo=True,
                habilitado=True,
            ).values_list('modulo__codigo', flat=True)
        )

    @classmethod
    def user_has_feature(cls, user, codigo, *, tenant=None):
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        tenant = tenant or getattr(getattr(user, 'perfil', None), 'empresa', None)
        return cls.has_feature(tenant, codigo)

    @classmethod
    def enabled_features_for_user(cls, user, *, tenant=None):
        if not user or not user.is_authenticated:
            return frozenset()
        if user.is_superuser:
            return frozenset(
                Modulo.objects.filter(ativo=True).values_list('codigo', flat=True)
            )
        tenant = tenant or getattr(getattr(user, 'perfil', None), 'empresa', None)
        return cls.enabled_features(tenant)

    @classmethod
    def home_url(cls, user, *, tenant=None):
        enabled = cls.enabled_features_for_user(user, tenant=tenant)
        destinations = (
            (Modulo.Codigo.ESTOQUE, 'estoque:index'),
            (Modulo.Codigo.EQUIPAMENTOS, 'estoque:estoque'),
            (Modulo.Codigo.INSUMOS, 'insumos:dashboard_base'),
            (Modulo.Codigo.CHECKLIST, 'insumos:lista_checklists'),
            (Modulo.Codigo.CHAMADOS, 'chamados:lista'),
            (Modulo.Codigo.TRANSFERENCIAS, 'estoque:lista_transferencias'),
            (Modulo.Codigo.EMPRESTIMOS, 'estoque:lista_emprestimos'),
            (Modulo.Codigo.SICK, 'estoque:sick'),
            (Modulo.Codigo.ORDENS_SERVICO, 'ordens_servico:lista'),
            (Modulo.Codigo.CATALOGO, 'compras:catalogo_empresa'),
            (Modulo.Codigo.TORY, 'estoque:assistente_operacional'),
        )
        for code, route in destinations:
            if code in enabled:
                return reverse(route)
        return reverse('estoque:caixa_comunicados')

    @classmethod
    def configure(cls, *, tenant, codigo, enabled, actor):
        if not getattr(actor, 'is_superuser', False):
            raise PermissionDenied(
                'Somente o Superuser pode configurar módulos de empresas.'
            )
        tenant_id = cls._tenant_id(tenant)
        if not tenant_id:
            raise ValidationError('Empresa inválida para configuração de módulo.')
        codigo = str(codigo or '').strip().lower()
        try:
            modulo = Modulo.objects.get(codigo=codigo)
        except Modulo.DoesNotExist as exc:
            raise ValidationError({'codigo': 'Módulo desconhecido.'}) from exc
        configuracao, _ = ModuloEmpresa.objects.update_or_create(
            empresa_id=tenant_id,
            modulo=modulo,
            defaults={
                'habilitado': bool(enabled),
                'configurado_por': actor,
            },
        )
        return configuracao

    @classmethod
    def provision_defaults(cls, tenant, *, using='default'):
        tenant_id = cls._tenant_id(tenant)
        if not tenant_id:
            return 0
        existing_module_ids = set(
            ModuloEmpresa.objects.using(using).filter(
                empresa_id=tenant_id
            ).values_list(
                'modulo_id', flat=True
            )
        )
        missing = [
            ModuloEmpresa(
                empresa_id=tenant_id,
                modulo_id=modulo_id,
                habilitado=True,
            )
            for modulo_id in Modulo.objects.using(using).filter(ativo=True).values_list(
                'pk', flat=True
            )
            if modulo_id not in existing_module_ids
        ]
        ModuloEmpresa.objects.using(using).bulk_create(
            missing,
            ignore_conflicts=True,
        )
        return len(missing)
