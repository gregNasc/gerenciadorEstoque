"""Catálogo público das permissões operacionais delegáveis.

O catálogo limita deliberadamente o que a tela administrativa pode conceder.
Permissões técnicas de ``auth``/``admin`` e privilégios de superusuário nunca
são expostos por este fluxo.
"""

PERMISSOES_OPERACIONAIS = (
    ('EQUIPAMENTOS', (
        ('estoque.visualizar_equipamentos', 'Visualizar'),
        ('estoque.cadastrar_equipamentos', 'Cadastrar'),
        ('estoque.editar_equipamentos', 'Editar'),
        ('estoque.baixar_equipamentos', 'Baixar'),
        ('estoque.transferir_equipamentos', 'Transferir'),
        ('estoque.visualizar_historico_equipamentos', 'Visualizar histórico'),
        ('estoque.gerenciar_sick_equipamentos', 'Gerenciar SICK'),
    )),
    ('TRANSFERÊNCIAS', (
        ('estoque.visualizar_transferencias', 'Visualizar'),
        ('estoque.criar_transferencias', 'Criar'),
        ('estoque.aprovar_transferencias', 'Aprovar'),
        ('estoque.receber_transferencias', 'Receber'),
        ('estoque.cancelar_transferencias', 'Cancelar'),
    )),
    ('CHECKLIST', (
        ('insumos.visualizar_checklists', 'Visualizar'),
        ('insumos.preencher_checklists', 'Preencher'),
        ('insumos.finalizar_checklists', 'Finalizar'),
        ('insumos.reabrir_checklists', 'Reabrir'),
        ('insumos.imprimir_checklists', 'Imprimir'),
        ('insumos.visualizar_historico_checklists', 'Visualizar históricos'),
    )),
    ('CHAMADOS', (
        ('chamados.abrir_chamado', 'Abrir'),
        ('chamados.atender_chamado', 'Atender'),
        ('chamados.supervisionar_chamado', 'Supervisão'),
        ('chamados.visualizar_dashboard_chamado', 'Visualizar dashboard'),
        ('chamados.configurar_chamado', 'Configurar'),
        ('chamados.visualizar_todos_chamados', 'Visualizar todos'),
        ('chamados.reabrir_chamado', 'Reabrir'),
        ('chamados.converter_chamado_sick', 'Converter em SICK'),
    )),
    ('USUÁRIOS', (
        ('estoque.visualizar_usuarios', 'Visualizar'),
        ('estoque.cadastrar_usuarios', 'Cadastrar'),
        ('estoque.editar_usuarios', 'Editar'),
        ('estoque.alterar_permissoes_usuario', 'Alterar permissões'),
        ('estoque.inativar_usuario', 'Inativar'),
        ('estoque.reativar_usuario', 'Reativar'),
        ('estoque.excluir_usuario', 'Excluir'),
    )),
    ('PRECIFICAÇÃO', (
        ('estoque.visualizar_preco_produto', 'Visualizar preços'),
        ('estoque.definir_preco_produto', 'Definir preço inicial'),
        ('estoque.alterar_preco_produto', 'Alterar preço existente'),
        ('estoque.importar_preco_produto', 'Importar em lote'),
        ('estoque.visualizar_historico_preco_produto', 'Consultar histórico'),
    )),
)

PERMISSOES_DELEGAVEIS = frozenset(
    codigo
    for _, permissoes in PERMISSOES_OPERACIONAIS
    for codigo, _ in permissoes
)


def catalogo_com_ids():
    """Resolve o catálogo depois das migrations, sem expor nomes técnicos."""
    from django.contrib.auth.models import Permission

    permissoes = {
        f'{item.content_type.app_label}.{item.codename}': item
        for item in Permission.objects.select_related('content_type').filter(
            content_type__app_label__in={'estoque', 'insumos', 'chamados'},
        )
        if f'{item.content_type.app_label}.{item.codename}' in PERMISSOES_DELEGAVEIS
    }
    return [
        {
            'grupo': grupo,
            'permissoes': [
                {
                    'codigo': codigo,
                    'label': label,
                    'id': permissoes[codigo].pk,
                }
                for codigo, label in itens
                if codigo in permissoes
            ],
        }
        for grupo, itens in PERMISSOES_OPERACIONAIS
    ]
