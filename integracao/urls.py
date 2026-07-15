from django.urls import path

from integracao import views


app_name = "integracao"

urlpatterns = [
    path(
        "inventory-planning/mapeamentos/",
        views.planning_mappings,
        name="planning_mappings",
    ),
]
