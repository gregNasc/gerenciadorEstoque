from django.urls import path

from ordens_servico import views


app_name = 'ordens_servico'

urlpatterns = [
    path('', views.lista, name='lista'),
    path('<int:pk>/', views.detalhe, name='detalhe'),
    path('<int:pk>/assinar/', views.assinar, name='assinar'),
    path('<int:pk>/imprimir/', views.imprimir, name='imprimir'),
    path('<int:pk>/pdf/', views.pdf, name='pdf'),
    path('anexos/<int:pk>/baixar/', views.baixar_anexo, name='baixar_anexo'),
]
