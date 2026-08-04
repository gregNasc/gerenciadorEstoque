from django.apps import AppConfig


class AuditoriasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'auditorias'
    verbose_name = 'Auditorias de equipamentos'

    def ready(self):
        from . import signals  # noqa: F401

