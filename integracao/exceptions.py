class InventoryPlanningError(Exception):
    """Erro base seguro para a integração Inventory Planning."""

class InventoryPlanningConfigurationError(InventoryPlanningError):
    pass

class InventoryPlanningAuthenticationError(InventoryPlanningError):
    pass

class InventoryPlanningResponseError(InventoryPlanningError):
    pass

class InventoryPlanningRateLimitError(InventoryPlanningError):
    pass

class InventoryPlanningTransportError(InventoryPlanningError):
    pass

class InventoryPortalError(Exception):
    """Erro base seguro para a leitura do Portal Inventory Brasil."""

class InventoryPortalConfigurationError(InventoryPortalError):
    pass

class InventoryPortalAuthenticationError(InventoryPortalError):
    pass

class InventoryPortalResponseError(InventoryPortalError):
    pass

class InventoryPortalTransportError(InventoryPortalError):
    pass


class DocusignError(Exception):
    """Erro base seguro para a integração DocuSign."""


class DocusignConfigurationError(DocusignError):
    pass


class DocusignAuthenticationError(DocusignError):
    pass


class DocusignResponseError(DocusignError):
    pass


class DocusignTransportError(DocusignError):
    pass


class DocusignWebhookError(DocusignError):
    pass


class TotvsError(Exception):
    """Erro base seguro para a integração TOTVS."""


class TotvsConfigurationError(TotvsError):
    pass


class TotvsUnsupportedProductError(TotvsConfigurationError):
    pass


class TotvsAuthenticationError(TotvsError):
    pass


class TotvsResponseError(TotvsError):
    pass


class TotvsRetryableError(TotvsError):
    def __init__(self, message='Falha temporária na integração.', *, retry_after_seconds=None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class TotvsAmbiguousResultError(TotvsError):
    """A API pode ter aceitado a operação; exige reconciliação antes de repetir."""
