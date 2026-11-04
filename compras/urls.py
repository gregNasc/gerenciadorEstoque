from django.urls import path

from compras import views


app_name = 'compras'

urlpatterns = [
    path('', views.lista_aquisicoes, name='aquisicao_lista'),
    path('catalogo/configurar/', views.configurar_catalogo_empresa, name='catalogo_empresa'),
    path('fornecedores/', views.fornecedores_empresa, name='fornecedores_empresa'),
    path(
        'cotacoes/solicitacoes/<int:solicitacao_id>/',
        views.cotacao_solicitacao,
        name='cotacao_solicitacao',
    ),
    path(
        'api/fornecedores-homologados/',
        views.api_fornecedores_homologados,
        name='api_fornecedores_homologados',
    ),
    path('nova/', views.criar_aquisicao, name='aquisicao_criar'),
    path('<int:pk>/', views.detalhe_aquisicao, name='aquisicao_detalhe'),
    path('<int:pk>/aprovar/', views.aprovar_aquisicao, name='aquisicao_aprovar'),
    path('<int:pk>/processar-xml/', views.processar_xml_nfe, name='aquisicao_processar_xml'),
    path(
        '<int:pk>/itens-nfe/<int:item_id>/confirmar-catalogo/',
        views.confirmar_item_nfe_catalogo,
        name='aquisicao_confirmar_item_nfe_catalogo',
    ),
    path('<int:pk>/documento/<str:tipo>/', views.documento_aquisicao, name='aquisicao_documento'),
    path('remessas/lista/', views.lista_remessas, name='remessa_lista'),
    path(
        'remessas/individualizacoes/',
        views.individualizacoes_pendentes,
        name='individualizacao_pendentes',
    ),
    path('remessas/nova/', views.criar_remessa, name='remessa_criar'),
    path('remessas/<int:pk>/', views.detalhe_remessa, name='remessa_detalhe'),
    path('remessas/<int:pk>/enviar/', views.enviar_remessa, name='remessa_enviar'),
    path('remessas/<int:pk>/confirmar/', views.confirmar_remessa, name='remessa_confirmar'),
    path(
        'remessas/<int:pk>/itens/<int:item_id>/individualizar/',
        views.individualizar_item_remessa,
        name='remessa_individualizar_item',
    ),
    path('valores/insumos/', views.valores_insumos, name='valores_insumos'),
    path('valores/equipamentos/', views.valores_equipamentos, name='valores_equipamentos'),
    path('valores/equipamentos/<int:equipamento_id>/preco/', views.alterar_preco_produto, name='alterar_preco_produto'),
    path('valores/equipamentos/template/', views.template_precificacao_equipamentos, name='template_precificacao_equipamentos'),
    path('valores/equipamentos/importar/', views.importar_precificacao_equipamentos, name='importar_precificacao_equipamentos'),
    path('catalogo/equipamentos/novo/', views.criar_produto_catalogo, name='criar_produto_catalogo'),
    path('api/catalogo/resolver/', views.resolver_codigo, name='resolver_codigo'),
]
