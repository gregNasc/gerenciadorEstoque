from django.urls import path

from integracao import views
from integracao.webhooks import docusign_webhook


app_name = "integracao"

urlpatterns = [
    path('docusign/webhook/', docusign_webhook, name='docusign_webhook'),
    path(
        "inventory-planning/mapeamentos/",
        views.planning_mappings,
        name="planning_mappings",
    ),
]
