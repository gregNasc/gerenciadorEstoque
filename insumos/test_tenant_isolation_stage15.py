from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from estoque.models import (
    Base,
    CapacidadeRelacionamentoEmpresa,
    Empresa,
    Perfil,
    RelacionamentoEmpresa,
)
from insumos.constants import GruposInsumos
from insumos.models import (
    CategoriaInsumo,
    ChecklistDiario,
    Cliente,
    HistoricoInsumo,
    Insumo,
    Inventario,
    MovimentacaoInsumo,
    SolicitacaoInsumo,
)
from insumos.policies import InsumosTenantPolicy
from insumos.services.movimentacao_service import MovimentacaoService


class Stage15TenantIsolationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company_a = Empresa.objects.create(nome='Empresa A Etapa 15')
        cls.company_b = Empresa.objects.create(nome='Empresa B Etapa 15')
        cls.base_a = Base.objects.create(empresa=cls.company_a, nome='Base A Etapa 15')
        cls.base_b = Base.objects.create(empresa=cls.company_b, nome='Base B Secreta Etapa 15')

        cls.admin_a = User.objects.create_user('admin.a.etapa15', password='Teste123!')
        cls.admin_a.perfil.role = Perfil.Role.ADMIN
        cls.admin_a.perfil.empresa = cls.company_a
        cls.admin_a.perfil.save()

        cls.admin_b = User.objects.create_user('admin.b.etapa15', password='Teste123!')
        cls.admin_b.perfil.role = Perfil.Role.ADMIN
        cls.admin_b.perfil.empresa = cls.company_b
        cls.admin_b.perfil.save()

        cls.functional = User.objects.create_user(
            'planejamento.sem.escopo.etapa15', password='Teste123!'
        )
        Group.objects.get_or_create(name=GruposInsumos.PLANEJAMENTO)[0].user_set.add(
            cls.functional
        )

        cls.superuser = User.objects.create_superuser(
            'superuser.etapa15', password='Teste123!'
        )
        cls.superuser.perfil.role = Perfil.Role.ADMIN
        cls.superuser.perfil.save(update_fields=['role'])

        cls.client_record = Cliente.objects.create(
            sigla='E15', nome='Cliente Etapa 15'
        )
        cls.inventory_a = Inventario.objects.create(
            cliente=cls.client_record,
            loja='A15',
            base=cls.base_a,
            data_inicio=timezone.localdate(),
            criado_por=cls.admin_a,
        )
        cls.inventory_b = Inventario.objects.create(
            cliente=cls.client_record,
            loja='B15-SECRETA',
            base=cls.base_b,
            data_inicio=timezone.localdate(),
            criado_por=cls.admin_b,
        )
        cls.checklist_a = ChecklistDiario.objects.create(
            inventario=cls.inventory_a,
            data_inicio=timezone.now(),
            criado_por=cls.admin_a,
            responsavel=cls.admin_a,
        )
        cls.checklist_b = ChecklistDiario.objects.create(
            inventario=cls.inventory_b,
            data_inicio=timezone.now(),
            criado_por=cls.admin_b,
            responsavel=cls.admin_b,
        )
        cls.request_a = SolicitacaoInsumo.objects.create(
            protocolo='INS-E15-A', base=cls.base_a, solicitante=cls.admin_a
        )
        cls.request_b = SolicitacaoInsumo.objects.create(
            protocolo='INS-E15-B-SECRETO', base=cls.base_b, solicitante=cls.admin_b
        )
        category = CategoriaInsumo.objects.create(nome='Categoria Etapa 15')
        cls.supply = Insumo.objects.create(
            descricao='Insumo Etapa 15',
            categoria=category,
            unidade_medida='UN',
        )

    def test_admin_is_limited_to_own_tenant_in_every_stage15_domain(self):
        self.assertEqual(
            set(InsumosTenantPolicy.inventories(self.admin_a, Inventario.objects.all())),
            {self.inventory_a},
        )
        self.assertEqual(
            set(InsumosTenantPolicy.checklists(self.admin_a, ChecklistDiario.objects.all())),
            {self.checklist_a},
        )
        self.assertEqual(
            set(InsumosTenantPolicy.requests(self.admin_a, SolicitacaoInsumo.objects.all())),
            {self.request_a},
        )

    def test_functional_group_without_explicit_tenant_scope_sees_nothing(self):
        self.assertFalse(
            InsumosTenantPolicy.inventories(
                self.functional, Inventario.objects.all()
            ).exists()
        )
        self.assertFalse(
            InsumosTenantPolicy.requests(
                self.functional, SolicitacaoInsumo.objects.all()
            ).exists()
        )

    def test_related_company_requires_profile_selection_and_exact_capability(self):
        relationship = RelacionamentoEmpresa.objects.create(
            empresa_origem=self.company_a,
            empresa_destino=self.company_b,
        )
        CapacidadeRelacionamentoEmpresa.objects.create(
            relacionamento=relationship,
            recurso=InsumosTenantPolicy.CHECKLISTS,
            acao=InsumosTenantPolicy.VIEW,
        )

        self.assertNotIn(
            self.checklist_b,
            InsumosTenantPolicy.checklists(
                self.admin_a, ChecklistDiario.objects.all()
            ),
        )
        self.admin_a.perfil.empresas_acesso_adicional.add(self.company_b)
        self.assertIn(
            self.checklist_b,
            InsumosTenantPolicy.checklists(
                self.admin_a, ChecklistDiario.objects.all()
            ),
        )
        self.assertNotIn(
            self.inventory_b,
            InsumosTenantPolicy.inventories(
                self.admin_a, Inventario.objects.all()
            ),
        )

    def test_forged_inventory_and_checklist_ids_return_404(self):
        self.client.force_login(self.admin_a)
        inventory_response = self.client.get(
            reverse('insumos:inventario_detalhes', args=[self.inventory_b.pk])
        )
        checklist_response = self.client.get(
            reverse('insumos:checklist_detail', args=[self.checklist_b.pk])
        )
        finalize_response = self.client.post(
            reverse('insumos:finalizar_checklist', args=[self.checklist_b.pk])
        )

        self.assertEqual(inventory_response.status_code, 404)
        self.assertEqual(checklist_response.status_code, 404)
        self.assertEqual(finalize_response.status_code, 404)

    def test_forged_stock_adjustment_cannot_touch_external_base(self):
        self.client.force_login(self.admin_a)
        response = self.client.post(reverse('insumos:ajustar_estoque_insumo'), {
            'base_id': self.base_b.pk,
            'insumo_id': self.supply.pk,
            'saldo_real': '10',
            'motivo': 'Tentativa externa',
            'senha': 'Teste123!',
        })

        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            MovimentacaoInsumo.objects.filter(
                base=self.base_b, usuario=self.admin_a
            ).exists()
        )

    def test_transaction_service_rejects_external_base(self):
        with self.assertRaises(PermissionDenied):
            MovimentacaoService.entrada(
                base=self.base_b,
                insumo=self.supply,
                quantidade='1',
                valor_unitario='1',
                usuario=self.admin_a,
            )
        self.assertFalse(
            MovimentacaoInsumo.objects.filter(
                base=self.base_b, usuario=self.admin_a
            ).exists()
        )

    def test_checklist_creation_form_and_post_do_not_cross_tenants(self):
        self.client.force_login(self.admin_a)
        form_response = self.client.get(reverse('estoque:checklist'))
        checklist_count = ChecklistDiario.objects.count()
        post_response = self.client.post(reverse('estoque:checklist'), {
            'inventario': self.inventory_b.pk,
            'quantidade_volumes': '1',
            'quantidade_equipamento_coletor': '0',
            'quantidade_equipamento_impressora': '0',
            'quantidade_equipamento_notebook': '0',
            'quantidade_equipamento_router': '0',
        })

        self.assertEqual(form_response.status_code, 200)
        self.assertNotContains(form_response, 'B15-SECRETA')
        self.assertNotContains(form_response, 'Base B Secreta Etapa 15')
        self.assertRedirects(post_response, reverse('estoque:checklist'))
        self.assertEqual(ChecklistDiario.objects.count(), checklist_count)

    def test_superuser_keeps_explicit_platform_scope(self):
        self.assertEqual(
            set(InsumosTenantPolicy.inventories(
                self.superuser, Inventario.objects.all()
            )),
            {self.inventory_a, self.inventory_b},
        )

    def test_superuser_creates_functional_profile_with_explicit_company_and_bases(self):
        self.client.force_login(self.superuser)
        response = self.client.post(reverse('estoque:cadastrar_usuario'), {
            'username': 'planejamento.com.escopo.etapa15',
            'password': 'Teste123!',
            'perfil_acesso': 'planejamento',
            'empresa': self.company_a.pk,
            'regionais': [self.base_a.pk],
            'bases_checklist': [self.base_a.pk],
            'is_active': 'on',
        })

        self.assertRedirects(response, reverse('estoque:cadastrar_usuario'))
        functional = User.objects.get(username='planejamento.com.escopo.etapa15')
        self.assertEqual(functional.perfil.empresa, self.company_a)
        self.assertEqual(set(functional.perfil.regionais.all()), {self.base_a})
        self.assertEqual(
            set(functional.perfil.bases_checklist.all()), {self.base_a}
        )
        self.assertTrue(
            functional.groups.filter(name=GruposInsumos.PLANEJAMENTO).exists()
        )
        self.assertEqual(
            set(InsumosTenantPolicy.inventories(
                functional, Inventario.objects.all()
            )),
            {self.inventory_a},
        )

    def test_functional_profile_without_explicit_scope_is_rejected(self):
        self.client.force_login(self.superuser)
        response = self.client.post(reverse('estoque:cadastrar_usuario'), {
            'username': 'planejamento.invalido.etapa15',
            'password': 'Teste123!',
            'perfil_acesso': 'planejamento',
            'is_active': 'on',
        })

        self.assertRedirects(response, reverse('estoque:cadastrar_usuario'))
        self.assertFalse(
            User.objects.filter(username='planejamento.invalido.etapa15').exists()
        )

    def test_tenant_admin_cannot_forge_functional_profile_assignment(self):
        self.client.force_login(self.admin_a)
        response = self.client.post(reverse('estoque:cadastrar_usuario'), {
            'username': 'planejamento.forjado.etapa15',
            'password': 'Teste123!',
            'perfil_acesso': 'planejamento',
            'empresa': self.company_a.pk,
            'regionais': [self.base_a.pk],
            'is_active': 'on',
        })

        self.assertRedirects(response, reverse('estoque:cadastrar_usuario'))
        self.assertFalse(
            User.objects.filter(username='planejamento.forjado.etapa15').exists()
        )

    def test_operational_history_is_scoped_by_base_and_global_history_is_fail_closed(self):
        history_a = HistoricoInsumo.objects.create(
            tipo='MOVIMENTACAO',
            usuario=self.admin_a,
            base=self.base_a,
            descricao='Histórico operacional A',
        )
        history_b = HistoricoInsumo.objects.create(
            tipo='MOVIMENTACAO',
            usuario=self.admin_b,
            base=self.base_b,
            descricao='Histórico operacional B secreto',
        )
        global_history = HistoricoInsumo.objects.create(
            tipo='PRECO',
            usuario=self.superuser,
            descricao='Histórico global de catálogo',
        )

        self.assertEqual(
            set(InsumosTenantPolicy.histories(
                self.admin_a, HistoricoInsumo.objects.all()
            )),
            {history_a},
        )
        self.assertEqual(
            set(InsumosTenantPolicy.histories(
                self.superuser, HistoricoInsumo.objects.all()
            )),
            {history_a, history_b, global_history},
        )
