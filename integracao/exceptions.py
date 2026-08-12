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
