from django.contrib import admin
from django.apps import apps
from .models import Inventario

# Registra todos
for model in apps.get_app_config('insumos').get_models():
    try:
        admin.site.register(model)
    except admin.sites.AlreadyRegistered:
        pass

# Remove o Inventario do registro automático
admin.site.unregister(Inventario)


@admin.register(Inventario)
class InventarioAdmin(admin.ModelAdmin):
    list_display = (
        "cliente",
        "base",
        "loja",
        "status",
        "data_inicio",
    )
    list_filter = (
        "status",
        "base",
    )
    search_fields = (
        "loja",
        "cliente__sigla",
    )