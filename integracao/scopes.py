from dataclasses import dataclass


class IntegrationScopeError(ValueError):
    pass


@dataclass(frozen=True)
class IntegrationExecutionScope:
    """Declara o limite de uma execução que conversa com um sistema externo."""

    PLATFORM_GLOBAL = "PLATFORM_GLOBAL"
    TENANT = "TENANT"

    kind: str
    source: str
    company_id: int | None = None

    def __post_init__(self):
        if not self.source:
            raise IntegrationScopeError("A origem da integração é obrigatória.")
        if self.kind == self.PLATFORM_GLOBAL and self.company_id is not None:
            raise IntegrationScopeError("Uma execução global não pode declarar empresa.")
        if self.kind == self.TENANT and self.company_id is None:
            raise IntegrationScopeError("Uma execução de tenant deve declarar empresa.")
        if self.kind not in {self.PLATFORM_GLOBAL, self.TENANT}:
            raise IntegrationScopeError("Tipo de escopo de integração inválido.")

    @classmethod
    def platform_global(cls, source):
        return cls(kind=cls.PLATFORM_GLOBAL, source=source)

    @classmethod
    def tenant(cls, source, company):
        company_id = getattr(company, "pk", company)
        return cls(kind=cls.TENANT, source=source, company_id=company_id)

    @classmethod
    def for_user(cls, source, user):
        if getattr(user, "is_superuser", False):
            return cls.platform_global(source)
        company = getattr(getattr(user, "perfil", None), "empresa", None)
        if company is None:
            raise IntegrationScopeError(
                "O usuário da integração não possui empresa declarada."
            )
        return cls.tenant(source, company)

    @property
    def is_platform_global(self):
        return self.kind == self.PLATFORM_GLOBAL

    def as_dict(self, *, filters=None):
        payload = {
            "kind": self.kind,
            "source": self.source,
        }
        if self.company_id is not None:
            payload["company_id"] = self.company_id
        if filters:
            payload["filters"] = dict(filters)
        return payload
