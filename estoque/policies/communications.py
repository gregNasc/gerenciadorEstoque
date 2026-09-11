from django.contrib.auth.models import User
from django.db.models import Q

from estoque.models import (
    Base,
    CapacidadeRelacionamentoEmpresa,
    Comunicado,
    Empresa,
    MensagemArquivo,
)
from estoque.security import secure_base_queryset, secure_company_queryset


class CommunicationAccessPolicy:
    """Escopo de mensagens, comunicados e respectivos arquivos."""

    RESOURCE = CapacidadeRelacionamentoEmpresa.Recurso.DOCUMENTACAO
    VIEW = CapacidadeRelacionamentoEmpresa.Acao.VISUALIZAR
    CREATE = CapacidadeRelacionamentoEmpresa.Acao.CRIAR

    @classmethod
    def companies(cls, user, *, action=CREATE):
        return secure_company_queryset(
            Empresa.objects.all(), user, resource=cls.RESOURCE, action=action
        )

    @classmethod
    def bases(cls, user, *, action=CREATE):
        return secure_base_queryset(
            Base.objects.all(), user, resource=cls.RESOURCE, action=action
        )

    @classmethod
    def users(cls, user, *, action=CREATE):
        if not user or not user.is_authenticated:
            return User.objects.none()
        if user.is_superuser:
            return User.objects.filter(is_active=True)
        empresas = cls.companies(user, action=action)
        return User.objects.filter(
            Q(pk=user.pk) | Q(perfil__empresa__in=empresas),
            is_active=True,
        ).distinct()

    @classmethod
    def comunicados(cls, user):
        if not user or not user.is_authenticated:
            return Comunicado.objects.none()
        qs = Comunicado.objects.all()
        if user.is_superuser:
            return qs
        empresas = cls.companies(user, action=cls.VIEW)
        return qs.filter(
            Q(usuarios=user)
            | Q(criado_por=user)
            | Q(enviar_para_todos=True, empresa__in=empresas)
            | Q(
                enviar_para_todos=True,
                empresa__isnull=True,
                criado_por__is_superuser=True,
            )
        ).distinct()

    @classmethod
    def message_files(cls, user):
        if not user or not user.is_authenticated:
            return MensagemArquivo.objects.none()
        return MensagemArquivo.objects.filter(
            Q(mensagem__destinos__usuario=user) | Q(mensagem__enviado_por=user)
        ).distinct()
