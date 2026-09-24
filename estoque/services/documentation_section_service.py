from estoque.models import SecaoDocumentacaoEmpresa
from django.utils.translation import gettext as _


class DocumentationSectionService:
    """Configuração fail-closed das áreas de documentação de cada tenant."""

    DEFAULT_LABELS = dict(SecaoDocumentacaoEmpresa.Codigo.choices)

    @classmethod
    def _company(cls, user=None, tenant=None):
        if tenant is not None:
            return tenant
        return getattr(getattr(user, 'perfil', None), 'empresa', None)

    @classmethod
    def configuration(cls, user=None, *, tenant=None):
        if getattr(user, 'is_superuser', False):
            return {
                code: {
                    'enabled': True,
                    'label': _(label),
                    'allow_legacy': True,
                }
                for code, label in cls.DEFAULT_LABELS.items()
            }

        company = cls._company(user, tenant)
        configured = {}
        if company is not None and getattr(company, 'ativa', False):
            configured = {
                section.codigo: section
                for section in SecaoDocumentacaoEmpresa.objects.filter(
                    empresa=company,
                )
            }
        return {
            code: {
                'enabled': bool(
                    code in configured and configured[code].habilitado
                ),
                'label': (
                    configured[code].nome_exibicao.strip()
                    if code in configured and configured[code].nome_exibicao.strip()
                    else _(label)
                ),
                'allow_legacy': bool(
                    code in configured
                    and configured[code].habilitado
                    and configured[code].permite_conteudo_global_legado
                ),
            }
            for code, label in cls.DEFAULT_LABELS.items()
        }

    @classmethod
    def is_enabled(cls, user, code, *, tenant=None):
        return cls.configuration(user, tenant=tenant).get(
            code, {}
        ).get('enabled', False)

    @classmethod
    def allows_legacy_global(cls, user, code, *, tenant=None):
        return cls.configuration(user, tenant=tenant).get(
            code, {}
        ).get('allow_legacy', False)

    @classmethod
    def context_for_request(cls, request):
        cached = getattr(request, '_documentation_sections_context', None)
        if cached is not None:
            return cached
        sections = cls.configuration(
            getattr(request, 'user', None),
            tenant=getattr(request, 'tenant', None),
        )
        context = {
            'tenant_documentation_sections': sections,
            'tenant_has_documentation_sections': any(
                section['enabled'] for section in sections.values()
            ),
        }
        request._documentation_sections_context = context
        return context
