from django.urls import path

from compras import views


app_name = 'compras'

urlpatterns = [
    path('', views.lista_aquisicoes, name='aquisicao_lista'),
    path('nova/', views.criar_aquisicao, name='aquisicao_criar'),
    path('<int:pk>/', views.detalhe_aquisicao, name='aquisicao_detalhe'),
    path('<int:pk>/aprovar/', views.aprovar_aquisicao, name='aquisicao_aprovar'),
    path('<int:pk>/documento/<str:tipo>/', views.documento_aquisicao, name='aquisicao_documento'),
    path('remessas/lista/', views.lista_remessas, name='remessa_lista'),
    path('remessas/nova/', views.criar_remessa, name='remessa_criar'),
    path('remessas/<int:pk>/', views.detalhe_remessa, name='remessa_detalhe'),
    path('remessas/<int:pk>/enviar/', views.enviar_remessa, name='remessa_enviar'),
    path('remessas/<int:pk>/confirmar/', views.confirmar_remessa, name='remessa_confirmar'),
    path('valores/insumos/', views.valores_insumos, name='valores_insumos'),
    path('valores/equipamentos/', views.valores_equipamentos, name='valores_equipamentos'),
    path('api/catalogo/resolver/', views.resolver_codigo, name='resolver_codigo'),
]
