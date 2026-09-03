from django.contrib import admin
from django.utils.html import format_html
from django.apps import apps
from django.contrib.admin.sites import AlreadyRegistered
from django.urls import reverse
from .models import (
    Produto,
    Equipamento,
    Transferencia,
    Sick,
    Historico,
    Descricao,
    Base,
    ComunicadoLeitura,
    DriverImpressora,
    ResolucaoDocumento,
    VideoDocumentacao,
)


# ================== MULTIEMPRESA ==================
class EmpresaAdminMixin:
    def get_queryset(self, request):
        qs = super().get_queryset(request)

        if request.user.is_superuser:
            return qs

        if hasattr(request.user, "perfil"):

            perfil = request.user.perfil
            empresa = perfil.empresa

            # MODELS COM REGIONAL
            if hasattr(self.model, "regional"):

                if perfil.is_admin:
                    return qs

                return qs.filter(
                    regional__in=perfil.regionais.all()
                )

            # BASE
            if self.model.__name__ == "Base":
                return qs.filter(empresa=empresa)

            # TRANSFERÊNCIAS
            if self.model.__name__ == "Transferencia":
                return qs.filter(
                    regional_origem__in=perfil.regionais.all()
                )

            # HISTÓRICO
            if self.model.__name__ == "Historico":
                return qs.filter(
                    equipamento__regional__in=perfil.regionais.all()
                )

        return qs.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser and hasattr(request.user, "perfil"):
            empresa = request.user.perfil.empresa

            if db_field.name == "regional":
                kwargs["queryset"] = Base.objects.filter(empresa=empresa)

            if db_field.name in ["regional_origem", "regional_destino"]:
                kwargs["queryset"] = Base.objects.filter(empresa=empresa)

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

@admin.register(Base)
class BaseAdmin(EmpresaAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'nome', 'empresa')
    list_filter = ('empresa',)
    search_fields = ('nome',)
    ordering = ('empresa', 'nome')

@admin.register(ComunicadoLeitura)
class ComunicadoLeituraAdmin(admin.ModelAdmin):
    list_display = (
        'comunicado',
        'usuario',
        'lido_em',
    )

    search_fields = (
        'usuario__username',
        'comunicado__titulo',
    )

    list_filter = (
        'lido_em',
    )

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
        "finalidade",
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

    list_filter = ("finalidade", "status", "regional", "produto__fabricante")

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
        'protocolo',
        'regional_origem',
        'regional_destino',
        'status',
        'created_at',
    )

    list_filter = (
        'status',
        'regional_origem',
        'regional_destino',
    )

    search_fields = (
        'protocolo',
        'regional_origem__nome',
        'regional_destino__nome',
    )

    ordering = ('-created_at',)


# ================== SICK ==================
@admin.register(Sick)
class SickAdmin(EmpresaAdminMixin, admin.ModelAdmin):
    list_display = (
        "equipamento",
        "categoria",
        "etapa",
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

    list_filter = ("etapa", "categoria", "data_ocorrencia", "resolvido_por")

    readonly_fields = ("data_ocorrencia",)

    def get_queryset(self, request):
        return super().get_queryset(request).exclude(
            tipo_destino=Sick.TipoDestino.TERCEIRIZADA,
        )

    def has_view_permission(self, request, obj=None):
        if obj and obj.tipo_destino == Sick.TipoDestino.TERCEIRIZADA:
            return False
        return super().has_view_permission(request, obj)

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

    def get_queryset(self, request):
        ids_terceirizados = list(Sick.objects.filter(
            tipo_destino=Sick.TipoDestino.TERCEIRIZADA,
        ).values_list('pk', flat=True))
        if not ids_terceirizados:
            return super().get_queryset(request)
        return super().get_queryset(request).exclude(
            detalhes__sick_id__in=ids_terceirizados,
        )

    list_filter = ("tipo_acao", "data", "usuario")

    search_fields = (
        "equipamento__numero_serie",
        "equipamento__patrimonio",
        "tipo_acao"
    )

    readonly_fields = ("data",)


@admin.register(DriverImpressora)
class DriverImpressoraAdmin(admin.ModelAdmin):
    list_display = (
        'titulo', 'fabricante', 'modelo', 'sistema_operacional',
        'arquitetura', 'versao', 'ativo', 'atualizado_em',
    )
    list_filter = ('ativo', 'fabricante', 'sistema_operacional', 'arquitetura')
    search_fields = ('titulo', 'fabricante', 'modelo', 'descricao')
    readonly_fields = ('nome_original', 'tamanho_bytes', 'criado_por', 'criado_em', 'atualizado_em')

    def save_model(self, request, obj, form, change):
        if 'arquivo' in form.changed_data and obj.arquivo:
            obj.nome_original = form.cleaned_data['arquivo'].name
            obj.tamanho_bytes = form.cleaned_data['arquivo'].size
        if not obj.criado_por_id:
            obj.criado_por = request.user
        super().save_model(request, obj, form, change)


@admin.register(ResolucaoDocumento)
class ResolucaoDocumentoAdmin(admin.ModelAdmin):
    list_display = (
        'titulo', 'fabricante', 'modelo', 'categoria', 'idioma', 'ativo',
        'atualizado_em',
    )
    list_filter = ('ativo', 'idioma', 'categoria', 'fabricante')
    search_fields = ('titulo', 'fabricante', 'modelo', 'resumo', 'tags')
    readonly_fields = ('nome_original', 'criado_por', 'criado_em', 'atualizado_em')

    def save_model(self, request, obj, form, change):
        if 'arquivo' in form.changed_data and obj.arquivo:
            obj.nome_original = form.cleaned_data['arquivo'].name
        if not obj.criado_por_id:
            obj.criado_por = request.user
        super().save_model(request, obj, form, change)


@admin.register(VideoDocumentacao)
class VideoDocumentacaoAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'origem', 'produto_codigo', 'categoria', 'ativo')
    list_filter = ('ativo', 'origem', 'categoria')
    search_fields = ('titulo', 'descricao', 'produto_codigo', 'tags')
    readonly_fields = ('criado_por', 'criado_em', 'atualizado_em')

    def save_model(self, request, obj, form, change):
        if not obj.criado_por_id:
            obj.criado_por = request.user
        super().save_model(request, obj, form, change)


# ================== DESCRIÇÃO ==================
@admin.register(Descricao)
class DescricaoAdmin(admin.ModelAdmin):
    list_display = ("descricao",)
    search_fields = ("descricao",)

app_models = apps.get_app_config('estoque').get_models()

for model in app_models:
    try:
        admin.site.register(model)
    except AlreadyRegistered:
        pass
