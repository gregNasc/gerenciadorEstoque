from django.urls import path

from integracao import views
from integracao.webhooks import docusign_webhook


app_name = "integracao"

urlpatterns = [
    path('caepi/', views.caepi_importacoes, name='caepi_importacoes'),
    path('caepi/<int:pk>/', views.caepi_detalhe, name='caepi_detalhe'),
    path('caepi/<int:pk>/publicar/', views.caepi_publicar, name='caepi_publicar'),
    path('docusign/webhook/', docusign_webhook, name='docusign_webhook'),
    path(
        "inventory-planning/mapeamentos/",
        views.planning_mappings,
        name="planning_mappings",
    ),
]
