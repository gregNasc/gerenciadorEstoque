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

