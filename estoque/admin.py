from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import (
    Produto,
    Equipamento,
    Transferencia,
    Sick,
    Historico,
    Descricao,
    Base,
)


# ================== MULTIEMPRESA ==================
class EmpresaAdminMixin:
    def get_queryset(self, request):
        qs = super().get_queryset(request)

        if request.user.is_superuser:
            return qs

        if hasattr(reques0t.user, "perfil"):
            empresa = request.user.perfil.empresa

            if hasattr(self.model, "regional"):
                return qs.filter(regional__empresa=empresa)

            if self.model.__name__ == "Base":
                return qs.filter(empresa=empresa)

            if self.model.__name__ == "Transferencia":
                return qs.filter(regional_origem__empresa=empresa)

            if self.model.__name__ == "Historico":
                return qs.filter(equipamento__regional__empresa=empresa)

        return qs.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser and hasattr(request.user, "perfil"):
            empresa = request.user.perfil.empresa

            if db_field.name == "regional":
                kwargs["queryset"] = Base.objects.filter(empresa=empresa)

            if db_field.name in ["regional_origem", "regional_destino"]:
                kwargs["queryset"] = Base.objects.filter(empresa=empresa)

        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ================== PRODUTO ==================
@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "descricao", "fabricante", "modelo")
    search_fields = ("codigo", "descricao", "fabricante", "modelo")
    list_filter = ("fabricante",)


# ================== EQUIPAMENTO ==================
@admin.register(Equipamento)
class EquipamentoAdmin(EmpresaAdminMixin, admin.ModelAdmin):
    list_display = (
        "numero_serie",
        "patrimonio",
        "get_produto",
        "regional",
        "status_colored",
        "preview_foto",
        "data_atualizacao"
    )

    list_select_related = ("produto", "regional")

    search_fields = (
        "numero_serie",
        "patrimonio",
        "produto__descricao",
        "produto__codigo",
        "responsavel"
    )

    list_filter = ("status", "regional", "produto__fabricante")

    readonly_fields = (
        "data_cadastro",
        "data_atualizacao",
        "preview_foto"
    )

    list_per_page = 50

    # -------- PRODUTO --------
    def get_produto(self, obj):
        return obj.produto.descricao
    get_produto.short_description = "Produto"
    get_produto.admin_order_field = "produto__descricao"

    # -------- STATUS COLORIDO --------
    def status_colored(self, obj):
        colors = {
            "ATIVO": "green",
            "SICK": "red",
            "TRANSFERENCIA": "orange",
            "MANUTENCAO": "blue",
            "BAIXA": "gray",
        }
        return format_html(
            '<b><span style="color:{};">{}</span></b>',
            colors.get(obj.status, "black"),
            obj.get_status_display()
        )
    status_colored.short_description = "Status"

    # -------- FOTO PREVIEW --------
    def preview_foto(self, obj):
        if obj.foto:
            return format_html(
                '<a href="{}" target="_blank">'
                '<img src="{}" style="height: 60px; border-radius: 6px;" />'
                '</a>',
                obj.foto.url,
                obj.foto.url
            )
        return "Sem foto"

    preview_foto.short_description = "Foto"


# ================== TRANSFERÊNCIA ==================
@admin.register(Transferencia)
class TransferenciaAdmin(admin.ModelAdmin):
        list_display = (
            'id',
            'regional_origem',
            'regional_destino',
            'status',
            'solicitado_por',
            'data_envio',
            'data_recebimento',
        )

        list_filter = (
            'status',
            'regional_origem',
            'regional_destino',
        )

        readonly_fields = (
            'regional_origem',
            'regional_destino',
            'status',
            'solicitado_por',
            #'recebido_por',
            'data_envio',
            'data_recebimento',
        )


# ================== SICK ==================
@admin.register(Sick)
class SickAdmin(EmpresaAdminMixin, admin.ModelAdmin):
    list_display = (
        "equipamento",
        "categoria",
        "motivo_resumido",
        "previsao_retorno",
        "data_ocorrencia",
        "status_sick"
    )

    list_select_related = ("equipamento", "equipamento__produto")

    search_fields = (
        "equipamento__numero_serie",
        "equipamento__patrimonio",
        "motivo",
        "categoria"
    )

    list_filter = ("categoria", "data_ocorrencia", "resolvido_por")

    readonly_fields = ("data_ocorrencia",)

    def motivo_resumido(self, obj):
        return obj.motivo[:50] + "..." if len(obj.motivo) > 50 else obj.motivo
    motivo_resumido.short_description = "Motivo"

    def status_sick(self, obj):
        if obj.data_resolucao:
            return format_html('<span style="color: green;">RESOLVIDO</span>')
        return format_html('<span style="color: red;">PENDENTE</span>')
    status_sick.short_description = "Status"


# ================== HISTÓRICO ==================
@admin.register(Historico)
class HistoricoAdmin(EmpresaAdminMixin, admin.ModelAdmin):
    list_display = (
        "equipamento",
        "tipo_acao",
        "usuario",
        "data"
    )

    list_select_related = ("equipamento", "usuario")

    list_filter = ("tipo_acao", "data", "usuario")

    search_fields = (
        "equipamento__numero_serie",
        "equipamento__patrimonio",
        "tipo_acao"
    )

    readonly_fields = ("data",)


# ================== DESCRIÇÃO ==================
@admin.register(Descricao)
class DescricaoAdmin(admin.ModelAdmin):
    list_display = ("descricao",)
    search_fields = ("descricao",)