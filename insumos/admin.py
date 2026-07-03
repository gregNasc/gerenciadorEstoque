from django.contrib import admin
from .models import AlteracaoCalendario


@admin.register(AlteracaoCalendario)
class AlteracaoCalendarioAdmin(admin.ModelAdmin):
    list_display = ('data', 'cliente_sigla', 'loja', 'regional_nome', 'revisao', 'origem_bloco')
    list_filter = ('origem_bloco', 'data', 'base')
    search_fields = ('cliente_sigla', 'loja', 'descricao', 'regional_nome', 'solicitante')
