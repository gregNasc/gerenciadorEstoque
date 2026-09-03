from django.urls import path
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from . import views
from .views import lista_transferencias
from . import declaracao_views
from . import comunicacao_views

app_name = 'estoque'

urlpatterns = [

    # ---------------- AUTH ----------------
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html', redirect_authenticated_user=True), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),


    # ---------------- DASHBOARD ----------------
    path('', views.index, name='index'),
    path('assistente/', views.assistente_operacional, name='assistente_operacional'),


    # ---------------- ESTOQUE ----------------
    path('estoque/', views.estoque_view, name='estoque'),
    path('manuais/', views.manuais_view, name='manuais'),
    path('manuais/drivers/', views.drivers_impressoras_view, name='drivers_impressoras'),
    path('manuais/drivers/<int:driver_id>/arquivo/', views.driver_impressora_arquivo_view, name='driver_impressora_arquivo'),
    path('manuais/drivers/<int:driver_id>/desativar/', views.driver_impressora_desativar_view, name='driver_impressora_desativar'),
    path('documentacao/', views.documentacao_view, name='documentacao'),
    path('documentacao/resolucao/', views.documentacao_resolucao_view, name='documentacao_resolucao'),
    path('documentacao/resolucao/<int:documento_id>/arquivo/', views.documentacao_resolucao_arquivo_view, name='documentacao_resolucao_arquivo'),
    path('documentacao/resolucao/<int:documento_id>/desativar/', views.documentacao_resolucao_desativar_view, name='documentacao_resolucao_desativar'),
    path('documentacao/clientes/', views.documentacao_clientes_view, name='documentacao_clientes'),
    path('documentacao/clientes/<int:cliente_id>/', views.documentacao_cliente_detalhe_view, name='documentacao_cliente_detalhe'),
    path('documentacao/clientes/<int:cliente_id>/arquivo/', views.documentacao_cliente_arquivo_view, name='documentacao_cliente_arquivo'),
    path('documentacao/videos/', views.documentacao_videos_view, name='documentacao_videos'),
    path('documentacao/videos/<int:video_id>/desativar/', views.documentacao_video_desativar_view, name='documentacao_video_desativar'),
    path('cadastrar-produto/', views.cadastrar_equipamento_view, name='cadastrar_equipamento'),
    path('produtos-por-categoria/', views.produtos_por_categoria, name='produtos_por_categoria'),
    path('detalhes-produto/<int:produto_id>/', views.detalhes_produto, name='detalhes_produto'),
    path('equipamentos-por-regional/<int:produto_id>/<int:regional_id>/', views.equipamentos_por_regional, name='equipamentos_por_regional'),


    # ---------------- USUÁRIOS ----------------
    path('usuarios/cadastro/', views.gerenciar_usuarios, name='cadastrar_usuario'),


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
#    path('transferencias/', lista_transferencias, name='lista_transferencias'),
#    path('transferencias/criar/', views.transferencia_criar, name='transferencia_criar'),
#    path('transferir-em-lote/', views.transferir_em_lote, name='transferir_em_lote'),
#    path('transferir-lote/', views.transferir_em_lote, name='transferir_lote'),
    path('receber-transferencia/<int:transferencia_id>/', views.receber_transferencia, name='receber_transferencia'),
    path('transferencias/<int:id>/', views.transferencia_detalhe, name='transferencia_detalhe'),
    path('transferencias/separacao/', views.caixa_separacao, name='caixa_separacao'),
    path('transferencias/recebimentos/', views.caixa_transferencias, name='caixa_transferencias'),
    path('transferencias/', views.lista_transferencias, name='lista_transferencias'),
    path('transferencias/<int:id>/selecionados/', views.transferencia_selecionados, name='transferencia_selecionados'),
    path('solicitacoes/<int:solicitacao_id>/recusar/', views.recusar_solicitacao, name='recusar_solicitacao'),
    path('minhas-solicitacoes/', views.minhas_solicitacoes, name='minhas_solicitacoes'),


    # ---------------- SOLICITAÇÕES ----------------
    path('solicitacoes/', views.caixa_solicitacoes, name='caixa_solicitacoes'),
    path('solicitacoes/criar/', views.criar_solicitacao, name='criar_solicitacao'),
    path('solicitacoes/<int:solicitacao_id>/alocacao/', views.painel_alocacao, name='painel_alocacao'),


    # ---------------- API ----------------
    path('api/produto/<int:produto_id>/regionais/', views.api_regionais_produto, name='api_regionais_produto'),
    path('estoque/detalhes-regional/<int:regional_id>/', views.detalhes_regional_api, name='detalhes_regional_api'),
    path('estoque/api/kpis/', views.api_kpis_json, name='api_kpis_json'),
    path('regionais/json/', views.lista_regionais_json, name='lista_regionais_json'),

    # ---------------- MENSAGENS ----------------
    path('mensagens/', views.caixa_mensagens, name='caixa_mensagens'),
    path('mensagens/enviar/', views.enviar_mensagem, name='enviar_mensagem'),
    path('mensagens/<int:destino_id>/', views.visualizar_mensagem, name='visualizar_mensagem'),
    path('comunicados/', views.caixa_comunicados, name='caixa_comunicados'),
    path('comunicados/novo/', views.criar_comunicado, name='criar_comunicado'),
    path('comunicados/<int:comunicado_id>/', views.detalhe_comunicado, name='detalhe_comunicado'),
    path('comunicados/arquivos/<int:arquivo_id>/baixar/', comunicacao_views.baixar_arquivo_comunicado, name='baixar_arquivo_comunicado'),
    path('comunicados/ocultar/<int:comunicado_id>/', views.ocultar_comunicado, name='ocultar_comunicado'),
    path('perfil/comunicacoes/', comunicacao_views.preferencias_whatsapp, name='preferencias_whatsapp'),

    # ---------------- EMPRÉSTIMO --------------------
    path('emprestimos/', views.lista_emprestimos, name='lista_emprestimos'),
    path('emprestimos/novo/', views.criar_emprestimo, name='criar_emprestimo'),
    path('emprestimos/<int:emprestimo_id>/', views.detalhe_emprestimo, name='detalhe_emprestimo'),
#    path('emprestimos/<int:emprestimo_id>/aprovar/', views.aprovar_emprestimo, name='aprovar_emprestimo'),
#    path('emprestimos/<int:emprestimo_id>/itens/', views.adicionar_itens_emprestimo, name='adicionar_itens_emprestimo'),
    path('emprestimos/<int:emprestimo_id>/receber/', views.receber_emprestimo, name='receber_emprestimo'),
    path('emprestimos/<int:emprestimo_id>/devolver/', views.devolver_emprestimo, name='devolver_emprestimo'),
#    path('emprestimos/<int:emprestimo_id>/enviar/', views.enviar_emprestimo, name='enviar_emprestimo'),
    path('emprestimos/<int:emprestimo_id>/confirmar-devolucao/', views.receber_devolucao_emprestimo, name='receber_devolucao_emprestimo'),

    # ---------------- DECLARAÇÃO DOS CORREIOS ----------------
    path('transferencias/<int:transferencia_id>/declaracao/', declaracao_views.declaracao_transferencia, name='declaracao_transferencia'),
    path('emprestimos/<int:emprestimo_id>/declaracao/', declaracao_views.declaracao_emprestimo, name='declaracao_emprestimo'),
    path('declaracoes/<int:declaracao_id>/', declaracao_views.declaracao_detalhe, name='declaracao_detalhe'),
    path('declaracoes/<int:declaracao_id>/emitir/', declaracao_views.emitir_declaracao, name='emitir_declaracao'),
    path('declaracoes/<int:declaracao_id>/pdf/', declaracao_views.baixar_declaracao, name='baixar_declaracao'),
    path('declaracoes/<int:declaracao_id>/substituir/', declaracao_views.substituir_declaracao, name='substituir_declaracao'),
    path('integracoes/whatsapp/webhook/', comunicacao_views.whatsapp_webhook, name='whatsapp_webhook'),

    # ---------------- PASSWORD RESET ----------------
    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='registration/estoque_password_reset_form.html',
        email_template_name='registration/estoque_password_reset_email.txt',
        subject_template_name='registration/password_reset_subject.txt',
        success_url=reverse_lazy('estoque:password_reset_done')
    ), name='password_reset'),

    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='registration/estoque_password_reset_done.html'
    ), name='password_reset_done'),

    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='registration/estoque_password_reset_confirm.html',
        success_url=reverse_lazy('estoque:password_reset_complete')
    ), name='password_reset_confirm'),

    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='registration/estoque_password_reset_complete.html'
    ), name='password_reset_complete'),

    # ---------------- EDIÇÃO ----------------
    path('equipamento/<int:equipamento_id>/editar/', views.editar_equipamento, name='editar_equipamento'),
    path('checklist/', views.checklist_view, name='checklist'),
    path('api/equipamentos-disponiveis/', views.get_equipamentos_disponiveis, name='api_equipamentos'),
    path('api/lotes-tags-disponiveis/', views.get_lotes_tags_disponiveis, name='api_lotes_tags'),
]
