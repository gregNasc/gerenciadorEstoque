from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from estoque.models import Base, Empresa, Perfil
from estoque.services.assistente_operacional_service import AssistenteOperacionalService
from insumos.models import Cliente, Inventario
from integracao.models import (
    InventoryPlanningEventBinding,
    InventoryPlanningSyncRun,
    PlanningClient,
    PlanningClientBinding,
    PlanningEvent,
    PlanningInventoryType,
    PlanningOperationalBaseBinding,
    PlanningRegion,
    PlanningRegionBinding,
    PlanningStore,
)


class ToryPlanningTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.tomorrow = timezone.localdate() + timedelta(days=1)
        self.company = Empresa.objects.create(nome="Empresa Tory Planning")
        self.base_campinas = Base.objects.create(
            nome="SP INT CPN",
            empresa=self.company,
        )
        self.base_sul = Base.objects.create(
            nome="SP SUL",
            empresa=self.company,
        )
        self.admin = User.objects.create_user("tory_planning_admin")
        Perfil.objects.update_or_create(
            user=self.admin,
            defaults={"role": Perfil.Role.ADMIN},
        )
        self.admin.refresh_from_db()
        self.operator = User.objects.create_user("tory_planning_operator")
        operator_profile, _ = Perfil.objects.update_or_create(
            user=self.operator,
            defaults={
                "empresa": self.company,
                "role": Perfil.Role.OPERADOR,
            },
        )
        operator_profile.regionais.add(self.base_campinas)
        self.operator.refresh_from_db()

        self.parent_type = self._type("type-parent", "INVENTÁRIO OFICIAL", "PAI")
        self.child_type = self._type("type-child", "ARRUMAÇÃO", "FILHO")
        self.region_campinas = self._region("region-campinas", "CAMPINAS", "SP")
        self.region_sul = self._region("region-sul", "SP SUL", "SP")
        PlanningRegionBinding.objects.create(
            planning_region=self.region_campinas,
            local_base=self.base_campinas,
            confirmed_by=self.admin,
        )
        PlanningRegionBinding.objects.create(
            planning_region=self.region_sul,
            local_base=self.base_sul,
            confirmed_by=self.admin,
        )
        self.external_client = PlanningClient.objects.create(
            external_id="client-oxx",
            trade_name="OXXO",
            synced_at=self.now,
            last_seen_at=self.now,
        )
        self.local_oxxo = Cliente.objects.create(sigla="OXX", nome="OXXO")
        PlanningClientBinding.objects.create(
            planning_client=self.external_client,
            local_client=self.local_oxxo,
        )
        self.store_campinas = self._store(
            "store-campinas",
            "OXX-CAMP-17",
            "CAMPINAS",
            self.region_campinas,
        )
        self.store_sul = self._store(
            "store-sul",
            "OXX-SUL-58",
            "SÃO PAULO",
            self.region_sul,
        )
        self.event_campinas = self._event(
            "event-campinas-001",
            self.store_campinas,
            self.region_campinas,
            pieces=260000,
            people=12,
        )
        self.event_sul = self._event(
            "event-sul-001",
            self.store_sul,
            self.region_sul,
            pieces=180000,
            people=9,
        )

    def _region(self, external_id, name, state):
        return PlanningRegion.objects.create(
            external_id=external_id,
            name=name,
            state=state,
            synced_at=self.now,
            last_seen_at=self.now,
        )

    def _type(self, external_id, name, kind):
        return PlanningInventoryType.objects.create(
            external_id=external_id,
            name=name,
            kind=kind,
            synced_at=self.now,
            last_seen_at=self.now,
        )

    def _store(self, external_id, code, city, region):
        return PlanningStore.objects.create(
            external_id=external_id,
            client=self.external_client,
            region=region,
            code=code,
            name=code,
            city=city,
            state="SP",
            synced_at=self.now,
            last_seen_at=self.now,
        )

    def _event(
        self,
        external_id,
        store,
        region,
        *,
        pieces,
        people,
        inventory_type=None,
        parent=None,
        hour=22,
        status="PLANNED",
    ):
        return PlanningEvent.objects.create(
            external_id=external_id,
            status=status,
            planned_at=timezone.make_aware(
                datetime.combine(self.tomorrow, time(hour, 0)),
            ),
            planned_pieces=pieces,
            planned_headcount=people,
            parent=parent,
            parent_external_id=parent.external_id if parent else "",
            store=store,
            client=self.external_client,
            region=region,
            inventory_type=inventory_type or self.parent_type,
            synced_at=self.now,
            last_seen_at=self.now,
            sensitive_data_filtered=True,
        )

    def test_lists_tomorrow_from_official_planning_source(self):
        result = AssistenteOperacionalService.responder(
            self.admin,
            "Quais inventários temos amanhã?",
        )

        self.assertEqual(result["contexto"]["intencao"], "planejamento")
        self.assertIn("OXX-CAMP-17", result["resposta"])
        self.assertIn("260.000", result["resposta"])
        self.assertIn("Fonte: Inventory Planning", result["resposta"])
        self.assertTrue(result["acoes"])

    def test_keeps_period_and_changes_region_in_continuation(self):
        first = AssistenteOperacionalService.responder(
            self.admin,
            "Quais inventários temos amanhã?",
        )
        in_campinas = AssistenteOperacionalService.responder(
            self.admin,
            "E em Campinas?",
            contexto=first["contexto"],
        )
        highest = AssistenteOperacionalService.responder(
            self.admin,
            "Qual tem maior previsão de peças?",
            contexto=in_campinas["contexto"],
        )

        self.assertEqual(in_campinas["contexto"]["data"], self.tomorrow.isoformat())
        self.assertIn("OXX-CAMP-17", in_campinas["resposta"])
        self.assertNotIn("OXX-SUL-58", in_campinas["resposta"])
        self.assertEqual(highest["contexto"]["external_event_id"], "event-campinas-001")
        self.assertIn("260.000", highest["resposta"])

    def test_shows_parent_and_child_without_assuming_child_execution(self):
        child = self._event(
            "event-child-001",
            self.store_campinas,
            self.region_campinas,
            pieces=1000,
            people=2,
            inventory_type=self.child_type,
            parent=self.event_campinas,
            hour=18,
        )

        result = AssistenteOperacionalService.responder(
            self.admin,
            "Mostre os eventos PAI e FILHO de amanhã",
        )

        self.assertIn(self.event_campinas.external_id, result["resposta"])
        self.assertIn(child.external_id, result["resposta"])
        self.assertIn("não presumo que tenham checklist ou execução própria", result["resposta"])

    def test_compares_planned_with_explicitly_bound_local_execution(self):
        inventory = Inventario.objects.create(
            cliente=self.local_oxxo,
            loja="17",
            base=self.base_campinas,
            data_inicio=self.tomorrow,
            criado_por=self.admin,
            pessoas=13,
            total_pecas=278000,
            inicio_real=timezone.make_aware(
                datetime.combine(self.tomorrow, time(20, 0)),
            ),
            fim_real=timezone.make_aware(
                datetime.combine(self.tomorrow + timedelta(days=1), time(5, 40)),
            ),
            custo_hora_pessoa=Decimal("30.00"),
            status="FINALIZADO",
        )
        InventoryPlanningEventBinding.objects.create(
            planning_event=self.event_campinas,
            inventory=inventory,
        )
        first = AssistenteOperacionalService.responder(
            self.admin,
            "Qual tem maior previsão de peças amanhã?",
        )
        compared = AssistenteOperacionalService.responder(
            self.admin,
            "E o planejado versus realizado?",
            contexto=first["contexto"],
        )

        self.assertIn("260.000", compared["resposta"])
        self.assertIn("278.000", compared["resposta"])
        self.assertIn("+18.000", compared["resposta"])
        self.assertIn("Inventory Planning", compared["resposta"])
        self.assertIn("gerenciadorEstoque", compared["resposta"])

    def test_availability_and_sporadic_simulation_are_hypotheses_only(self):
        first = AssistenteOperacionalService.responder(
            self.admin,
            "Qual tem maior previsão de peças amanhã?",
        )
        availability = AssistenteOperacionalService.responder(
            self.admin,
            "Temos pessoas suficientes?",
            contexto=first["contexto"],
        )
        simulation = AssistenteOperacionalService.responder(
            self.admin,
            "E se adicionarmos cinco avulsos?",
            contexto=availability["contexto"],
        )

        self.assertIn("Ainda não posso confirmar", availability["resposta"])
        self.assertIn("fase posterior", availability["resposta"])
        self.assertIn("de 12 para 17 pessoas", simulation["resposta"])
        self.assertIn("não altera a escala nem o planejamento", simulation["resposta"])

    def test_operator_only_sees_bound_regions_in_existing_scope(self):
        PlanningOperationalBaseBinding.objects.create(
            planning_client=self.external_client,
            planning_region=self.region_campinas,
            local_base=self.base_campinas,
        )
        result = AssistenteOperacionalService.responder(
            self.operator,
            "Quais inventários temos amanhã?",
        )

        self.assertIn("OXX-CAMP-17", result["resposta"])
        self.assertNotIn("OXX-SUL-58", result["resposta"])

    def test_reports_unavailable_source_without_breaking(self):
        PlanningEvent.objects.all().delete()
        InventoryPlanningSyncRun.objects.create(
            endpoint="events",
            status=InventoryPlanningSyncRun.Status.FAILED,
            error_code="InventoryPlanningTransportError",
            error_message="mensagem técnica não deve aparecer",
            finished_at=timezone.now(),
        )

        result = AssistenteOperacionalService.responder(
            self.admin,
            "Quais inventários temos amanhã?",
        )

        self.assertIn("não estão disponíveis no momento", result["resposta"])
        self.assertIn("dados locais de execução", result["resposta"])
        self.assertNotIn("mensagem técnica", result["resposta"])

    def test_query_is_read_only(self):
        before = (
            self.event_campinas.status,
            self.event_campinas.planned_pieces,
            Inventario.objects.count(),
        )

        AssistenteOperacionalService.responder(
            self.admin,
            "Quais inventários temos amanhã?",
        )
        self.event_campinas.refresh_from_db()

        self.assertEqual(
            before,
            (
                self.event_campinas.status,
                self.event_campinas.planned_pieces,
                Inventario.objects.count(),
            ),
        )

    def test_responds_when_called_tory_and_keeps_the_question_intent(self):
        result = AssistenteOperacionalService.responder(
            self.admin,
            "Tory, quais inventários temos amanhã?",
        )

        self.assertEqual(result["contexto"]["intencao"], "planejamento")
        self.assertIn("Claro, tory_planning_admin.", result["resposta"])
        self.assertIn("OXX-CAMP-17", result["resposta"])

    def test_tory_name_alone_is_a_natural_greeting(self):
        result = AssistenteOperacionalService.responder(self.admin, "Tory")

        self.assertEqual(result["contexto"]["intencao"], "saudacao")
        self.assertIn("Estou por aqui", result["resposta"])
        self.assertIn("planejamento, execução, estoque, insumos e custos", result["resposta"])
        self.assertNotIn("tory_planning_admin, oi", result["resposta"].lower())

    def test_campinas_can_show_multiple_operations_and_oxxo_disambiguates(self):
        oxxo_base = Base.objects.create(
            nome="OXXO SP INT CPN X",
            empresa=self.company,
        )
        local_regular = Cliente.objects.create(sigla="BSA", nome="BARBOSA")
        PlanningOperationalBaseBinding.objects.create(
            planning_client=self.external_client,
            planning_region=self.region_campinas,
            local_base=oxxo_base,
        )
        external_regular = PlanningClient.objects.create(
            external_id="client-regular",
            trade_name="BARBOSA",
            synced_at=self.now,
            last_seen_at=self.now,
        )
        PlanningClientBinding.objects.create(
            planning_client=external_regular,
            local_client=local_regular,
        )
        PlanningOperationalBaseBinding.objects.create(
            planning_client=external_regular,
            planning_region=self.region_campinas,
            local_base=self.base_campinas,
        )
        regular_store = PlanningStore.objects.create(
            external_id="store-regular-campinas",
            client=external_regular,
            region=self.region_campinas,
            code="BSA-CAMP-22",
            name="BSA-CAMP-22",
            city="CAMPINAS",
            state="SP",
            synced_at=self.now,
            last_seen_at=self.now,
        )
        PlanningEvent.objects.create(
            external_id="event-regular-campinas",
            status="PLANNED",
            planned_at=timezone.make_aware(datetime.combine(self.tomorrow, time(21, 0))),
            planned_pieces=120000,
            planned_headcount=8,
            store=regular_store,
            client=external_regular,
            region=self.region_campinas,
            inventory_type=self.parent_type,
            synced_at=self.now,
            last_seen_at=self.now,
            sensitive_data_filtered=True,
        )

        ambiguous = AssistenteOperacionalService.responder(
            self.admin,
            "Tory, quais inventários temos amanhã em Campinas?",
        )
        oxxo_only = AssistenteOperacionalService.responder(
            self.admin,
            "Tory, quais inventários OXXO temos amanhã em Campinas?",
        )

        self.assertIn("OXX-CAMP-17", ambiguous["resposta"])
        self.assertIn("BSA-CAMP-22", ambiguous["resposta"])
        self.assertIn("OXX-CAMP-17", oxxo_only["resposta"])
        self.assertNotIn("BSA-CAMP-22", oxxo_only["resposta"])
