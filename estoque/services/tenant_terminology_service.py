from estoque.models import Modulo, ModuloEmpresa, TermoEmpresa


class TenantTerminologyService:
    """Resolve rótulos de apresentação sem alterar códigos internos."""

    DEFAULTS = {
        TermoEmpresa.Chave.EMPRESA: ('Empresa', 'Empresas'),
        TermoEmpresa.Chave.EQUIPAMENTO: ('Equipamento', 'Equipamentos'),
        TermoEmpresa.Chave.BASE: ('Base', 'Bases'),
        TermoEmpresa.Chave.REGIONAL: ('Regional', 'Regionais'),
        TermoEmpresa.Chave.MANUTENCAO: ('Manutenção', 'Manutenções'),
        TermoEmpresa.Chave.USUARIO: ('Usuário', 'Usuários'),
        TermoEmpresa.Chave.DOCUMENTACAO: ('Documentação', 'Documentações'),
    }

    MODULE_DEFAULTS = dict(Modulo.Codigo.choices)

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
                'singular': singular,
                'plural': plural,
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
        return labels

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
            'Ativos'
            if stock_label == cls.MODULE_DEFAULTS[Modulo.Codigo.ESTOQUE]
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
