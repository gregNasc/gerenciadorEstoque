from django.urls import path

from chamados import views


app_name = 'chamados'

urlpatterns = [
    path('', views.lista, name='lista'),
    path('novo/', views.criar, name='criar'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('exportar/', views.exportar, name='exportar'),
    path('<int:pk>/', views.detalhe, name='detalhe'),
    path('<int:pk>/assumir/', views.assumir, name='assumir'),
    path('<int:pk>/mensagem/', views.mensagem, name='mensagem'),
    path('<int:pk>/status/', views.alterar_status, name='alterar_status'),
    path('anexos/<int:pk>/baixar/', views.baixar_anexo, name='baixar_anexo'),
]
