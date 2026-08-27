from functools import wraps

from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import models
from django.db.models import UniqueConstraint
from django.db.models.signals import pre_save
from django.dispatch import receiver


BUSINESS_APP_LABELS = {
    'auditorias',
    'chamados',
    'compras',
    'core',
    'estoque',
    'insumos',
    'integracao',
    'ordens_servico',
}

EXPLICIT_BUSINESS_FIELDS = {
    ('auth.User', 'first_name'),
    ('auth.User', 'last_name'),
}

CASE_INSENSITIVE_UNIQUE_FIELDS = {
    ('auth.User', 'username'),
}

TECHNICAL_NAME_PARTS = {
    'email',
    'endpoint',
    'external_id',
    'hash',
    'idempotency',
    'import_key',
    'link',
    'password',
    'provider_message_id',
    'senha',
    'secret',
    'token',
    'url',
    'user_agent',
}

TECHNICAL_MODEL_FIELDS = {
    ('chamados.AliasUsuario', 'alias_normalizado'),
    ('chamados.PendenciaVinculoLider', 'texto_normalizado'),
    ('chamados.ChamadoAnexo', 'nome_original'),
    ('estoque.ComunicadoEntrega', 'destino'),
    ('estoque.ComunicadoEntrega', 'provedor'),
    ('estoque.ComunicadoEntrega', 'template_codigo'),
    ('estoque.ComunicadoEntrega', 'ultimo_erro'),
    ('estoque.MensagemArquivo', 'nome_original'),
    ('insumos.AlteracaoCalendario', 'arquivo'),
    ('insumos.ClienteChecklistDocumento', 'nome_original'),
    ('insumos.HistoricoCadastroInsumo', 'campo'),
    ('integracao.InventoryPlanningSyncRun', 'data_source'),
    ('integracao.InventoryPlanningSyncRun', 'error_code'),
    ('integracao.InventoryPlanningSyncRun', 'error_message'),
    ('integracao.PlanningEvent', 'data_source'),
    ('integracao.PlanningEvent', 'materialization_error'),
    ('integracao.PlanningClient', 'data_source'),
    ('integracao.PlanningInventoryType', 'data_source'),
    ('integracao.PlanningRegion', 'data_source'),
    ('integracao.PlanningStore', 'data_source'),
}


def campo_de_texto_de_negocio(model, field):
    if (model._meta.label, field.name) in EXPLICIT_BUSINESS_FIELDS:
        return True
    if model._meta.app_label not in BUSINESS_APP_LABELS:
        return False
    if not isinstance(field, (models.CharField, models.TextField)):
        return False
    if isinstance(field, (models.EmailField, models.URLField)) or field.choices:
        return False
    if (model._meta.label, field.name) in TECHNICAL_MODEL_FIELDS:
        return False
    nome = field.name.lower()
    return not any(parte in nome for parte in TECHNICAL_NAME_PARTS)


def modelo_com_texto_de_negocio(model):
    return any(campo_de_texto_de_negocio(model, field) for field in model._meta.concrete_fields)


def normalizar_textos_de_negocio(instance):
    for field in instance._meta.concrete_fields:
        if not campo_de_texto_de_negocio(instance.__class__, field):
            continue
        valor = getattr(instance, field.attname, None)
        if isinstance(valor, str):
            setattr(instance, field.attname, valor.upper())


def _query_sem_instancia(instance):
    queryset = instance.__class__._default_manager.all()
    if instance.pk is not None:
        queryset = queryset.exclude(pk=instance.pk)
    return queryset


def _lookup_sem_diferenciar_caixa(model, nomes, instance):
    lookup = {}
    for nome in nomes:
        field = model._meta.get_field(nome)
        valor = getattr(instance, field.attname, None)
        if valor in (None, ''):
            return None
        sufixo = '__iexact' if isinstance(field, (models.CharField, models.TextField)) else ''
        lookup[f'{field.name}{sufixo}'] = valor
    return lookup


def validar_unicidade_sem_diferenciar_caixa(instance):
    model = instance.__class__
    if not modelo_com_texto_de_negocio(model):
        return

    queryset = _query_sem_instancia(instance)
    erros = {}

    for field in model._meta.concrete_fields:
        if not field.unique or not (
            campo_de_texto_de_negocio(model, field)
            or (model._meta.label, field.name) in CASE_INSENSITIVE_UNIQUE_FIELDS
        ):
            continue
        valor = getattr(instance, field.attname, None)
        if valor not in (None, '') and queryset.filter(**{f'{field.name}__iexact': valor}).exists():
            erros[field.name] = f'JÁ EXISTE UM REGISTRO COM ESTE {field.verbose_name}.'

    grupos = list(model._meta.unique_together)
    grupos.extend(
        constraint.fields
        for constraint in model._meta.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.fields
        and constraint.condition is None
        and not constraint.expressions
    )
    for nomes in grupos:
        if not any(
            campo_de_texto_de_negocio(model, model._meta.get_field(nome))
            for nome in nomes
        ):
            continue
        lookup = _lookup_sem_diferenciar_caixa(model, nomes, instance)
        if lookup and queryset.filter(**lookup).exists():
            campos = ', '.join(model._meta.get_field(nome).verbose_name for nome in nomes)
            erros.setdefault(
                NON_FIELD_ERRORS,
                f'JÁ EXISTE UM REGISTRO COM A MESMA COMBINAÇÃO DE {campos}.',
            )

    if erros:
        raise ValidationError(erros)


def instalar_normalizacao_caixa_alta():
    from django.apps import apps

    for model in apps.get_models():
        if not modelo_com_texto_de_negocio(model):
            continue
        if getattr(model, '_normalizacao_caixa_alta_instalada', False):
            continue

        clean_original = model.clean

        @wraps(clean_original)
        def clean_com_normalizacao(self, _clean_original=clean_original):
            normalizar_textos_de_negocio(self)
            _clean_original(self)
            validar_unicidade_sem_diferenciar_caixa(self)

        model.clean = clean_com_normalizacao
        model._normalizacao_caixa_alta_instalada = True


@receiver(pre_save, dispatch_uid='estoque.normalizar_textos_caixa_alta')
def normalizar_antes_de_salvar(sender, instance, raw=False, **kwargs):
    if raw or not modelo_com_texto_de_negocio(sender):
        return
    normalizar_textos_de_negocio(instance)
    validar_unicidade_sem_diferenciar_caixa(instance)
