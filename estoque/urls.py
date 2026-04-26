from django.urls import path
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from . import views
from .views import lista_transferencias

app_name = 'estoque'

urlpatterns = [

    # ---------------- AUTH ----------------
    path('login/', auth_views.LoginView.as_view(
        template_name='registration/login.html',
        redirect_authenticated_user=True,
    ), name='login'),

    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),


    # ---------------- DASHBOARD ----------------
    path('', views.index, name='index'),


    # ---------------- ESTOQUE ----------------
    path('estoque/', views.estoque_view, name='estoque'),
    path('cadastrar-produto/', views.cadastrar_equipamento_view, name='cadastrar_equipamento'),
    path('produtos-por-categoria/', views.produtos_por_categoria, name='produtos_por_categoria'),
    path('detalhes-produto/<int:produto_id>/', views.detalhes_produto, name='detalhes_produto'),
    path('equipamentos-por-regional/<int:produto_id>/<int:regional_id>/', views.equipamentos_por_regional, name='equipamentos_por_regional'),


    # ---------------- USUÁRIOS ----------------
    path('usuarios/cadastro/', views.cadastrar_usuario, name='cadastrar_usuario'),


    # ---------------- SICK ----------------
    path('sick/', views.sick_view, name='sick'),
    path('marcar-sick/<int:equipamento_id>/', views.marcar_sick_ajax, name='marcar_sick'),


    # ---------------- HISTÓRICO ----------------
    path('historico/', views.historico_view, name='historico'),
    path('historico/<int:historico_id>/', views.historico_detalhes_view, name='historico_detalhes'),
    path('historico-modal/<int:equipamento_id>/', views.historico_equipamento_modal, name='historico_modal'),
    path('historico/exportar/excel/', views.exportar_historico_excel, name='exportar_historico_excel'),
    path('historico/exportar/pdf/', views.exportar_historico_pdf, name='exportar_historico_pdf'),


    # ---------------- TRANSFERÊNCIAS ----------------
    path('transferencias/', lista_transferencias, name='lista_transferencias'),
    path('transferir-em-lote/', views.transferir_em_lote, name='transferir_em_lote'),
    path('transferir-lote/', views.transferir_em_lote, name='transferir_lote'),
    path('receber-transferencia/<int:transferencia_id>/', views.receber_transferencia, name='receber_transferencia'),


    # ---------------- SOLICITAÇÕES ----------------
    path('solicitacoes/', views.caixa_solicitacoes, name='caixa_solicitacoes'),
    path('solicitacoes/criar/', views.criar_solicitacao, name='criar_solicitacao'),

    path(
        'solicitacoes/<int:solicitacao_id>/alocacao/',
        views.painel_alocacao,
        name='painel_alocacao'
    ),


    # ---------------- API ----------------
    path('api/produto/<int:produto_id>/regionais/', views.api_regionais_produto, name='api_regionais_produto'),
    path('estoque/detalhes-regional/<int:regional_id>/', views.detalhes_regional_api, name='detalhes_regional_api'),
    path('estoque/api/kpis/', views.api_kpis_json, name='api_kpis_json'),
    path('regionais/json/', views.lista_regionais_json, name='lista_regionais_json'),


    # ---------------- PASSWORD RESET ----------------
    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='registration/password_reset_form.html',
        email_template_name='registration/password_reset_email.html',
        success_url=reverse_lazy('estoque:password_reset_done')
    ), name='password_reset'),

    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='registration/password_reset_done.html'
    ), name='password_reset_done'),

    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='registration/password_reset_confirm.html',
        success_url=reverse_lazy('estoque:password_reset_complete')
    ), name='password_reset_confirm'),

    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='registration/password_reset_complete.html'
    ), name='password_reset_complete'),
]