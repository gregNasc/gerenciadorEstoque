from django.urls import path

from . import views

app_name = 'auditorias'

urlpatterns = [
    path('', views.campanha_lista, name='campanha_lista'),
    path('nova/', views.campanha_criar, name='campanha_criar'),
    path('<int:campanha_id>/', views.campanha_detalhe, name='campanha_detalhe'),
    path('<int:campanha_id>/agendar/', views.campanha_agendar, name='campanha_agendar'),
    path('bases/<int:auditoria_base_id>/iniciar/', views.base_iniciar, name='base_iniciar'),
    path('bases/<int:auditoria_base_id>/coleta/', views.coleta, name='coleta'),
    path('bases/<int:auditoria_base_id>/leituras/', views.registrar_leitura, name='registrar_leitura'),
    path('bases/<int:auditoria_base_id>/enviar/', views.base_enviar, name='base_enviar'),
    path('bases/<int:auditoria_base_id>/reabrir/', views.base_reabrir, name='base_reabrir'),
    path('bases/<int:auditoria_base_id>/finalizar/', views.base_finalizar, name='base_finalizar'),
    path('bases/<int:auditoria_base_id>/solicitar-correcao/', views.base_solicitar_correcao, name='base_solicitar_correcao'),
    path('bases/<int:auditoria_base_id>/divergencias/', views.divergencias, name='divergencias'),
    path('divergencias/<int:divergencia_id>/', views.divergencia_detalhe, name='divergencia_detalhe'),
    path('divergencias/<int:divergencia_id>/manter/', views.divergencia_manter, name='divergencia_manter'),
    path('divergencias/<int:divergencia_id>/transferir/', views.divergencia_transferir, name='divergencia_transferir'),
    path('divergencias/<int:divergencia_id>/responder/', views.divergencia_responder, name='divergencia_responder'),
    path('bases/<int:auditoria_base_id>/relatorio.<str:formato>', views.relatorio_base, name='relatorio_base'),
    path('<int:campanha_id>/relatorio.<str:formato>', views.relatorio_campanha, name='relatorio_campanha'),
]
