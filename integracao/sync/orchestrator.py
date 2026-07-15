from integracao.services.inventory_planning_service import InventoryPlanningService


class InventoryPlanningSyncOrchestrator(InventoryPlanningService):
    """Ponto de entrada dos jobs de sincronização em lote."""

