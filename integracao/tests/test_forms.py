from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from estoque.models import Base, Empresa
from insumos.forms import InventarioForm
from insumos.models import Cliente, Inventario
from integracao.models import InventoryPlanningEventBinding, PlanningEvent


class SynchronizedInventoryFormTests(TestCase):
    def test_external_planning_fields_are_disabled(self):
        user = User.objects.create_user("sync-form")
        empresa = Empresa.objects.create(nome="Empresa")
        base = Base.objects.create(nome="Base", empresa=empresa)
        cliente = Cliente.objects.create(sigla="CLI", nome="Cliente")
        inventory = Inventario.objects.create(
            cliente=cliente,
            loja="1",
            base=base,
            data_inicio=date(2026, 7, 16),
            criado_por=user,
        )
        now = timezone.now()
        event = PlanningEvent.objects.create(
            external_id="event-form",
            data_source="INVENTORY_PLANNING",
            synced_at=now,
            last_seen_at=now,
            status="PLANNED",
            planned_at=now,
        )
        InventoryPlanningEventBinding.objects.create(
            planning_event=event,
            inventory=inventory,
        )

        form = InventarioForm(instance=inventory)

        for field_name in InventarioForm.EXTERNAL_PLANNING_FIELDS:
            if field_name in form.fields:
                self.assertTrue(form.fields[field_name].disabled, field_name)
        self.assertFalse(form.fields["inicio_real"].disabled)
        self.assertFalse(form.fields["total_pecas"].disabled)

