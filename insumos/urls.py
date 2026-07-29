from django.urls import path
from django.shortcuts import redirect
from insumos.views.dashboard_base import dashboard_base
from insumos.views.dashboard_planejamento import dashboard_planejamento
from insumos.views.dashboard_financeiro import dashboard_financeiro
from insumos.views import api
from insumos.views.api import importar_excel
from insumos.views.api import insumos_por_categoria
from insumos.views import custos
from insumos.views import solicitacoes

app_name = 'insumos'

urlpatterns = [
    path('', lambda request: redirect('insumos:dashboard_base')),
    path('dashboard/base/', dashboard_base, name='dashboard_base'),
    path('dashboard/planejamento/', dashboard_planejamento, name='dashboard_planejamento'),
    path('dashboard/financeiro/', dashboard_financeiro, name='dashboard_financeiro'),
    path('custos/', custos.dashboard_custos, name='dashboard_custos'),
    path('custos/precos/', custos.precos_insumos, name='precos_insumos'),
    path('custos/fornecedores/', custos.fornecedores_insumos, name='fornecedores_insumos'),
    path('custos/pesquisa/', custos.pesquisa_precos_online, name='pesquisa_precos_online'),
    path(
        'custos/pesquisa/ofertas/<int:oferta_id>/usar/',
        custos.usar_oferta_como_preco,
        name='usar_oferta_como_preco',
    ),
    path('solicitacoes/', solicitacoes.lista_solicitacoes, name='lista_solicitacoes_insumo'),
    path('solicitacoes/nova/', solicitacoes.criar_solicitacao, name='criar_solicitacao_insumo'),
    path('solicitacoes/<int:pk>/', solicitacoes.detalhe_solicitacao, name='detalhe_solicitacao'),
    path('solicitacoes/<int:pk>/decidir/', solicitacoes.decidir_solicitacao, name='decidir_solicitacao'),
    path('api/kpis/inventarios/', api.kpi_inventarios),
    path('api/bi/consumo-base/', api.consumo_por_base),
    path('api/bi/ranking-insumos/', api.ranking_insumos),
    path('api/bi/consumo-mes/', api.consumo_por_mes),
    path('insumos/', api.lista_insumos, name='lista_insumos'),
    path('insumos/cadastrar/', api.cadastrar_insumo, name='cadastrar_insumos'),
    path('insumos/<int:pk>/editar/', api.editar_insumo, name='editar_insumos'),
    path('api/insumos-por-categoria/', insumos_por_categoria, name='insumos_por_categoria'),
    path('estoque/', api.estoque_insumos, name='estoque_insumos'),
    path('importar-excel/', api.importar_excel, name='importar_excel'),
    path('api/inventario/<int:inventario_id>/', api.inventario_detalhes, name='inventario_detalhes'),
    path('gerenciar-inventarios/', api.gerenciar_inventarios, name='gerenciar_inventarios'),
    path('inventarios/', api.lista_inventarios, name='lista_inventarios'),
    path('inventarios/<int:pk>/editar/', api.editar_inventario, name='editar_inventario'),
    path('exportar-excel/', api.exportar_excel, name='exportar_excel'),
    path('api/insumos-por-base/', api.insumos_por_base, name='api_insumos_por_base'),
    path('checklists/', api.lista_checklists, name='lista_checklists'),
    path('checklist/<int:pk>/finalizar/', api.finalizar_checklist, name='finalizar_checklist'),
    path('checklist/<int:pk>/', api.checklist_detail, name='checklist_detail'),
    path('checklist/<int:pk>/imprimir/', api.imprimir_checklist, name='imprimir_checklist'),
    path('checklist/<int:pk>/modelo.xlsx', api.exportar_checklist_modelo, name='exportar_checklist_modelo'),
    path('checklist/<int:pk>/editar-itens/', api.editar_itens_checklist, name='editar_itens_checklist'),
    path('checklist/<int:pk>/editar/', api.editar_checklist, name='editar_checklist'),
    path('api/ultimo-checklist/', api.ultimo_checklist_por_loja, name='api_ultimo_checklist'),
    path('estoque/ajustar/', api.ajustar_estoque_insumo, name='ajustar_estoque_insumo'),
]
