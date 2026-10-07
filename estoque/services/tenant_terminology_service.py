from estoque.models import Modulo, ModuloEmpresa, TermoEmpresa
from django.utils.translation import gettext, gettext_noop


class TenantTerminologyService:
    """Resolve rótulos de apresentação sem alterar códigos internos."""

    DEFAULTS = {
        TermoEmpresa.Chave.EMPRESA: (gettext_noop('Empresa'), gettext_noop('Empresas')),
        TermoEmpresa.Chave.EQUIPAMENTO: (gettext_noop('Equipamento'), gettext_noop('Equipamentos')),
        TermoEmpresa.Chave.BASE: (gettext_noop('Base'), gettext_noop('Bases')),
        TermoEmpresa.Chave.REGIONAL: (gettext_noop('Regional'), gettext_noop('Regionais')),
        TermoEmpresa.Chave.MANUTENCAO: (gettext_noop('Manutenção'), gettext_noop('Manutenções')),
        TermoEmpresa.Chave.USUARIO: (gettext_noop('Usuário'), gettext_noop('Usuários')),
        TermoEmpresa.Chave.DOCUMENTACAO: (gettext_noop('Documentação'), gettext_noop('Documentações')),
    }

    MODULE_DEFAULTS = {
        Modulo.Codigo.ESTOQUE: gettext_noop('Estoque'),
        Modulo.Codigo.EQUIPAMENTOS: gettext_noop('Equipamentos'),
        Modulo.Codigo.SICK: gettext_noop('SICK'),
        Modulo.Codigo.TRANSFERENCIAS: gettext_noop('Transferências'),
        Modulo.Codigo.EMPRESTIMOS: gettext_noop('Empréstimos'),
        Modulo.Codigo.INSUMOS: gettext_noop('Insumos'),
        Modulo.Codigo.CHECKLIST: gettext_noop('Checklist'),
        Modulo.Codigo.CHAMADOS: gettext_noop('Chamados'),
        Modulo.Codigo.ORDENS_SERVICO: gettext_noop('Ordens de serviço'),
        Modulo.Codigo.CATALOGO: gettext_noop('Catálogo'),
        Modulo.Codigo.TORY: gettext_noop('Tory'),
        Modulo.Codigo.AUDITORIAS: gettext_noop('Auditorias'),
        Modulo.Codigo.DOCUMENTACAO: gettext_noop('Documentação'),
        Modulo.Codigo.USUARIOS: gettext_noop('Usuários'),
        Modulo.Codigo.CADASTROS: gettext_noop('Cadastros'),
    }
    DASHBOARD_DEFAULT = gettext_noop('Ativos')

    @classmethod
    def labels(cls, company):
        """Retorna todos os termos do tenant com uma única consulta."""
        configured = {}
        if company is not None:
            configured = {
                term.chave: term
                for term in TermoEmpresa.objects.filter(empresa=company).only(
                    'chave', 'valor_singular', 'valor_plural',
                )
            }

        labels = {}
        for key, defaults in cls.DEFAULTS.items():
            term = configured.get(key)
            singular = (
                term.valor_singular.strip()
                if term is not None and term.valor_singular.strip()
                else defaults[0]
            )
            plural = (
                term.valor_plural.strip()
                if term is not None and term.valor_plural.strip()
                else defaults[1]
            )
            labels[key] = {
                'singular': gettext(singular),
                'plural': gettext(plural),
            }
        return labels

    @classmethod
    def module_labels(cls, company):
        """Retorna o nome de apresentação dos módulos sem expor seus códigos."""
        labels = dict(cls.MODULE_DEFAULTS)
        if company is None:
            return labels

        configurations = ModuloEmpresa.objects.filter(
            empresa=company,
        ).select_related('modulo').only(
            'nome_exibicao', 'modulo__codigo', 'modulo__nome',
        )
        for configuration in configurations:
            custom_name = configuration.nome_exibicao.strip()
            if custom_name:
                labels[configuration.modulo.codigo] = custom_name
        return {
            code: gettext(label)
            for code, label in labels.items()
        }

    @classmethod
    def context_for_request(cls, request):
        """Monta e memoriza a terminologia no escopo do request atual."""
        company = getattr(request, 'tenant', None)
        company_id = getattr(company, 'pk', None)
        cache = getattr(request, '_tenant_terminology_context_cache', None)
        if cache is not None and cache['company_id'] == company_id:
            return cache['context']

        module_labels = cls.module_labels(company)
        stock_label = module_labels[Modulo.Codigo.ESTOQUE]
        dashboard_label = (
            gettext(cls.DASHBOARD_DEFAULT)
            if stock_label == gettext(cls.MODULE_DEFAULTS[Modulo.Codigo.ESTOQUE])
            else stock_label
        )
        context = {
            'tenant_labels': cls.labels(company),
            'tenant_module_labels': module_labels,
            'tenant_dashboard_label': dashboard_label,
        }
        request._tenant_terminology_context_cache = {
            'company_id': company_id,
            'context': context,
        }
        return context

    @classmethod
    def label(cls, company, key, *, plural=False):
        labels = cls.labels(company)
        values = labels.get(key)
        if values is None:
            return str(key)
        return values['plural' if plural else 'singular']
