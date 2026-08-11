from django.apps import AppConfig


class EstoqueConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'estoque'

    def ready(self):
        import estoque.signals
        from estoque.text_normalization import instalar_normalizacao_caixa_alta

        instalar_normalizacao_caixa_alta()
