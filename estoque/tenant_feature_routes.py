from estoque.models import DeclaracaoCorreios, Modulo, SecaoDocumentacaoEmpresa


class TenantFeatureRoutePolicy:
    """Resolve a feature exigida por cada ponto de entrada HTTP."""

    NAMESPACE_FEATURES = {
        'auditorias': Modulo.Codigo.AUDITORIAS,
        'chamados': Modulo.Codigo.CHAMADOS,
        'compras': Modulo.Codigo.CATALOGO,
        'insumos': Modulo.Codigo.INSUMOS,
        'integracao': Modulo.Codigo.INSUMOS,
        'ordens_servico': Modulo.Codigo.ORDENS_SERVICO,
    }

    ROUTE_FEATURES = {
        ('estoque', 'index'): Modulo.Codigo.ESTOQUE,
        ('estoque', 'assistente_operacional'): Modulo.Codigo.TORY,

        ('estoque', 'estoque'): Modulo.Codigo.EQUIPAMENTOS,
        ('estoque', 'cadastrar_equipamento'): (
            Modulo.Codigo.EQUIPAMENTOS,
            Modulo.Codigo.CADASTROS,
        ),
        ('estoque', 'produtos_por_categoria'): (
            Modulo.Codigo.EQUIPAMENTOS,
            Modulo.Codigo.CADASTROS,
        ),
        ('estoque', 'detalhes_produto'): Modulo.Codigo.EQUIPAMENTOS,
        ('estoque', 'equipamento_arquivo'): Modulo.Codigo.EQUIPAMENTOS,
        ('estoque', 'equipamentos_por_regional'): Modulo.Codigo.EQUIPAMENTOS,
        ('estoque', 'historico'): Modulo.Codigo.EQUIPAMENTOS,
        ('estoque', 'historico_detalhes'): Modulo.Codigo.EQUIPAMENTOS,
        ('estoque', 'historico_modal'): Modulo.Codigo.EQUIPAMENTOS,
        ('estoque', 'exportar_historico_excel'): Modulo.Codigo.EQUIPAMENTOS,
        ('estoque', 'exportar_historico_pdf'): Modulo.Codigo.EQUIPAMENTOS,
        ('estoque', 'editar_equipamento'): (
            Modulo.Codigo.EQUIPAMENTOS,
            Modulo.Codigo.CADASTROS,
        ),
        ('estoque', 'api_regionais_produto'): Modulo.Codigo.EQUIPAMENTOS,
        ('estoque', 'detalhes_regional_api'): Modulo.Codigo.EQUIPAMENTOS,

        ('estoque', 'sick'): Modulo.Codigo.SICK,
        ('estoque', 'marcar_sick'): Modulo.Codigo.SICK,

        ('estoque', 'receber_transferencia'): Modulo.Codigo.TRANSFERENCIAS,
        ('estoque', 'transferencia_detalhe'): Modulo.Codigo.TRANSFERENCIAS,
        ('estoque', 'caixa_separacao'): Modulo.Codigo.TRANSFERENCIAS,
        ('estoque', 'caixa_transferencias'): Modulo.Codigo.TRANSFERENCIAS,
        ('estoque', 'lista_transferencias'): Modulo.Codigo.TRANSFERENCIAS,
        ('estoque', 'transferencia_selecionados'): Modulo.Codigo.TRANSFERENCIAS,
        ('estoque', 'recusar_solicitacao'): Modulo.Codigo.TRANSFERENCIAS,
        ('estoque', 'minhas_solicitacoes'): Modulo.Codigo.TRANSFERENCIAS,
        ('estoque', 'caixa_solicitacoes'): Modulo.Codigo.TRANSFERENCIAS,
        ('estoque', 'criar_solicitacao'): Modulo.Codigo.TRANSFERENCIAS,
        ('estoque', 'painel_alocacao'): Modulo.Codigo.TRANSFERENCIAS,
        ('estoque', 'declaracao_transferencia'): Modulo.Codigo.TRANSFERENCIAS,
        ('estoque', 'lista_emprestimos'): Modulo.Codigo.EMPRESTIMOS,
        ('estoque', 'criar_emprestimo'): Modulo.Codigo.EMPRESTIMOS,
        ('estoque', 'detalhe_emprestimo'): Modulo.Codigo.EMPRESTIMOS,
        ('estoque', 'receber_emprestimo'): Modulo.Codigo.EMPRESTIMOS,
        ('estoque', 'devolver_emprestimo'): Modulo.Codigo.EMPRESTIMOS,
        ('estoque', 'receber_devolucao_emprestimo'): Modulo.Codigo.EMPRESTIMOS,
        ('estoque', 'declaracao_emprestimo'): Modulo.Codigo.EMPRESTIMOS,

        ('estoque', 'checklist'): Modulo.Codigo.CHECKLIST,
        ('estoque', 'api_equipamentos'): Modulo.Codigo.CHECKLIST,
        ('estoque', 'api_lotes_tags'): Modulo.Codigo.CHECKLIST,

        ('estoque', 'api_kpis_json'): Modulo.Codigo.ESTOQUE,
        ('estoque', 'lista_regionais_json'): Modulo.Codigo.ESTOQUE,

        ('estoque', 'manuais'): Modulo.Codigo.DOCUMENTACAO,
        ('estoque', 'drivers_impressoras'): Modulo.Codigo.DOCUMENTACAO,
        ('estoque', 'driver_impressora_arquivo'): Modulo.Codigo.DOCUMENTACAO,
        ('estoque', 'driver_impressora_desativar'): Modulo.Codigo.DOCUMENTACAO,
        ('estoque', 'documentacao'): Modulo.Codigo.DOCUMENTACAO,
        ('estoque', 'documentacao_legado_arquivo'): Modulo.Codigo.DOCUMENTACAO,
        ('estoque', 'documentacao_resolucao'): Modulo.Codigo.DOCUMENTACAO,
        ('estoque', 'documentacao_resolucao_arquivo'): Modulo.Codigo.DOCUMENTACAO,
        ('estoque', 'documentacao_resolucao_desativar'): Modulo.Codigo.DOCUMENTACAO,
        ('estoque', 'documentacao_clientes'): Modulo.Codigo.DOCUMENTACAO,
        ('estoque', 'documentacao_cliente_detalhe'): Modulo.Codigo.DOCUMENTACAO,
        ('estoque', 'documentacao_cliente_arquivo'): Modulo.Codigo.DOCUMENTACAO,
        ('estoque', 'documentacao_videos'): Modulo.Codigo.DOCUMENTACAO,
        ('estoque', 'documentacao_video_desativar'): Modulo.Codigo.DOCUMENTACAO,
        ('estoque', 'cadastrar_usuario'): Modulo.Codigo.USUARIOS,

        ('insumos', 'dashboard_saude_equipamentos'): Modulo.Codigo.EQUIPAMENTOS,
        ('insumos', 'dashboard_saude_geral'): (
            Modulo.Codigo.INSUMOS,
            Modulo.Codigo.EQUIPAMENTOS,
        ),
        ('insumos', 'lista_checklists'): Modulo.Codigo.CHECKLIST,
        ('insumos', 'finalizar_checklist'): Modulo.Codigo.CHECKLIST,
        ('insumos', 'reabrir_checklist'): Modulo.Codigo.CHECKLIST,
        ('insumos', 'checklist_detail'): Modulo.Codigo.CHECKLIST,
        ('insumos', 'imprimir_checklist'): Modulo.Codigo.CHECKLIST,
        ('insumos', 'exportar_checklist_modelo'): Modulo.Codigo.CHECKLIST,
        ('insumos', 'editar_itens_checklist'): Modulo.Codigo.CHECKLIST,
        ('insumos', 'editar_checklist'): Modulo.Codigo.CHECKLIST,
        ('insumos', 'api_ultimo_checklist'): Modulo.Codigo.CHECKLIST,
        ('insumos', 'api_insumos_por_base'): Modulo.Codigo.CHECKLIST,
        ('insumos', 'lista_insumos'): (
            Modulo.Codigo.INSUMOS,
            Modulo.Codigo.CADASTROS,
        ),
        ('insumos', 'cadastrar_insumos'): (
            Modulo.Codigo.INSUMOS,
            Modulo.Codigo.CADASTROS,
        ),
        ('insumos', 'editar_insumos'): (
            Modulo.Codigo.INSUMOS,
            Modulo.Codigo.CADASTROS,
        ),

        ('compras', 'valores_insumos'): Modulo.Codigo.INSUMOS,
        ('compras', 'valores_equipamentos'): Modulo.Codigo.EQUIPAMENTOS,
        ('compras', 'alterar_preco_produto'): Modulo.Codigo.EQUIPAMENTOS,
        ('compras', 'template_precificacao_equipamentos'): Modulo.Codigo.EQUIPAMENTOS,
        ('compras', 'importar_precificacao_equipamentos'): Modulo.Codigo.EQUIPAMENTOS,
        ('compras', 'criar_produto_catalogo'): (
            Modulo.Codigo.CATALOGO,
            Modulo.Codigo.CADASTROS,
        ),
        ('compras', 'resolver_codigo'): (
            Modulo.Codigo.CATALOGO,
            Modulo.Codigo.CADASTROS,
        ),
    }

    DECLARATION_ROUTES = {
        ('estoque', 'declaracao_detalhe'),
        ('estoque', 'emitir_declaracao'),
        ('estoque', 'baixar_declaracao'),
        ('estoque', 'substituir_declaracao'),
    }

    ROUTE_DOCUMENTATION_SECTIONS = {
        ('estoque', 'documentacao'): SecaoDocumentacaoEmpresa.Codigo.BIBLIOTECA,
        ('estoque', 'manuais'): SecaoDocumentacaoEmpresa.Codigo.MANUAIS,
        ('estoque', 'drivers_impressoras'): SecaoDocumentacaoEmpresa.Codigo.DRIVERS,
        ('estoque', 'driver_impressora_arquivo'): SecaoDocumentacaoEmpresa.Codigo.DRIVERS,
        ('estoque', 'driver_impressora_desativar'): SecaoDocumentacaoEmpresa.Codigo.DRIVERS,
        ('estoque', 'documentacao_resolucao'): SecaoDocumentacaoEmpresa.Codigo.RESOLUCOES,
        ('estoque', 'documentacao_resolucao_arquivo'): SecaoDocumentacaoEmpresa.Codigo.RESOLUCOES,
        ('estoque', 'documentacao_resolucao_desativar'): SecaoDocumentacaoEmpresa.Codigo.RESOLUCOES,
        ('estoque', 'documentacao_clientes'): SecaoDocumentacaoEmpresa.Codigo.CHECKLISTS,
        ('estoque', 'documentacao_cliente_detalhe'): SecaoDocumentacaoEmpresa.Codigo.CHECKLISTS,
        ('estoque', 'documentacao_cliente_arquivo'): SecaoDocumentacaoEmpresa.Codigo.CHECKLISTS,
        ('estoque', 'documentacao_videos'): SecaoDocumentacaoEmpresa.Codigo.VIDEOS,
        ('estoque', 'documentacao_video_desativar'): SecaoDocumentacaoEmpresa.Codigo.VIDEOS,
    }

    @classmethod
    def required_documentation_section(cls, match):
        if not match:
            return None
        return cls.ROUTE_DOCUMENTATION_SECTIONS.get(
            (match.namespace or '', match.url_name or '')
        )

    @classmethod
    def required_features(cls, match, view_kwargs=None):
        if not match:
            return ()
        key = (match.namespace or '', match.url_name or '')
        if key in cls.DECLARATION_ROUTES:
            declaracao_id = (view_kwargs or {}).get('declaracao_id')
            operacao = (
                DeclaracaoCorreios.objects
                .filter(pk=declaracao_id)
                .values('transferencia_id', 'emprestimo_id')
                .first()
            )
            if not operacao:
                return ()
            codigo = (
                Modulo.Codigo.TRANSFERENCIAS
                if operacao['transferencia_id']
                else Modulo.Codigo.EMPRESTIMOS
            )
            return (codigo,)

        configured = cls.ROUTE_FEATURES.get(
            key,
            cls.NAMESPACE_FEATURES.get(key[0]),
        )
        if not configured:
            return ()
        if isinstance(configured, (tuple, list, set, frozenset)):
            return tuple(configured)
        return (configured,)

    @classmethod
    def feature_for_match(cls, match):
        features = cls.required_features(match)
        return features[0] if len(features) == 1 else None
