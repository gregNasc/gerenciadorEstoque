from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.test import TestCase

from estoque.models import (
    Base,
    CapacidadeRelacionamentoEmpresa,
    CategoriaEquipamentoEmpresa,
    Empresa,
    Equipamento,
    Perfil,
    Produto,
    RelacionamentoEmpresa,
    Transferencia,
)
from compras.models import CatalogoProdutoEmpresa
from estoque.services.assistente_operacional_service import AssistenteOperacionalService
from estoque.tenant_scope import TenantScope
from insumos.models import (
    CategoriaInsumo,
    FornecedorInsumo,
    Insumo,
    PrecoFornecedorInsumo,
    SolicitacaoInsumo,
)


class ToryTenantIsolationStage20Tests(TestCase):
    def setUp(self):
        self.brasil = Empresa.objects.create(
            nome='Inventory Brasil Tory 20', slug='inventory-brasil-tory-20'
        )
        self.latam = Empresa.objects.create(
            nome='Inventory LATAM Tory 20', slug='inventory-latam-tory-20'
        )
        self.oxxo = Empresa.objects.create(
            nome='OXXO Tory 20', slug='oxxo-tory-20'
        )
        self.antropic = Empresa.objects.create(
            nome='Antropic Tory 20', slug='antropic-tory-20'
        )
        self.bases = {
            'BR': Base.objects.create(nome='BASE BR TORY20', empresa=self.brasil),
            'LATAM': Base.objects.create(nome='BASE LATAM TORY20', empresa=self.latam),
            'OXXO': Base.objects.create(nome='BASE OXXO TORY20', empresa=self.oxxo),
            'ANTROPIC': Base.objects.create(
                nome='BASE ANTROPIC TORY20', empresa=self.antropic
            ),
        }
        produto = Produto.objects.create(
            codigo='PROD-TORY20',
            descricao='COLETOR TORY 20',
            fabricante='Inventory',
            modelo='T20',
            categoria='Coletores',
        )
        for empresa in (self.brasil, self.latam, self.oxxo, self.antropic):
            CategoriaEquipamentoEmpresa.objects.create(
                empresa=empresa,
                nome='Coletores',
                aliases=['coletor', 'coletores'],
                referencia_capacidade=True,
            )
            CatalogoProdutoEmpresa.objects.create(empresa=empresa, produto=produto)
        for codigo, base in self.bases.items():
            Equipamento.objects.create(
                produto=produto,
                numero_serie=f'SERIE-{codigo}-TORY20',
                patrimonio=f'PATRIMONIO-{codigo}-TORY20',
                regional=base,
                codigo=f'EQP-{codigo}-TORY20',
                status='ATIVO',
            )

        self.superuser = User.objects.create_superuser(
            username='superuser_tory20',
            email='superuser-tory20@example.test',
            password='senha-teste-tory20',
        )
        self.admin_brasil = self._user('admin_brasil_tory20', Perfil.Role.ADMIN, self.brasil)
        self.admin_latam = self._user('admin_latam_tory20', Perfil.Role.ADMIN, self.latam)
        self.admin_oxxo = self._user('admin_oxxo_tory20', Perfil.Role.ADMIN, self.oxxo)
        self.gestor = self._user(
            'gestor_brasil_tory20',
            Perfil.Role.GESTOR,
            self.brasil,
            bases=(self.bases['BR'],),
        )
        self.operador = self._user(
            'operador_brasil_tory20',
            Perfil.Role.OPERADOR,
            self.brasil,
            bases=(self.bases['BR'],),
        )

        self.admin_brasil.perfil.empresas_acesso_adicional.add(self.latam, self.oxxo)
        for destination in (self.latam, self.oxxo):
            relationship = RelacionamentoEmpresa.objects.create(
                empresa_origem=self.brasil,
                empresa_destino=destination,
                ativo=True,
                criado_por=self.superuser,
            )
            for resource in (
                CapacidadeRelacionamentoEmpresa.Recurso.TORY,
                CapacidadeRelacionamentoEmpresa.Recurso.EQUIPAMENTOS,
            ):
                CapacidadeRelacionamentoEmpresa.objects.create(
                    relacionamento=relationship,
                    recurso=resource,
                    acao=CapacidadeRelacionamentoEmpresa.Acao.VISUALIZAR,
                    criado_por=self.superuser,
                )

    @staticmethod
    def _user(username, role, company, *, bases=()):
        user = User.objects.create_user(username=username)
        profile, _ = Perfil.objects.update_or_create(
            user=user,
            defaults={'role': role, 'empresa': company},
        )
        profile.regionais.add(*bases)
        user.refresh_from_db()
        return user

    def _ask_equipment_question(self, user, *, context=None, scope=None):
        return AssistenteOperacionalService.responder(
            user,
            'Liste todos os equipamentos cadastrados',
            contexto=context,
            tenant_scope=scope or TenantScope.fresh_for_user(user),
        )['resposta']

    def test_same_question_never_expands_each_profile_scope(self):
        expected = {
            self.superuser: {'BR', 'LATAM', 'OXXO', 'ANTROPIC'},
            self.admin_brasil: {'BR', 'LATAM', 'OXXO'},
            self.admin_latam: {'LATAM'},
            self.admin_oxxo: {'OXXO'},
            self.gestor: {'BR'},
            self.operador: {'BR'},
        }
        all_codes = {'BR', 'LATAM', 'OXXO', 'ANTROPIC'}

        for user, visible_codes in expected.items():
            with self.subTest(username=user.username):
                response = self._ask_equipment_question(user)
                for code in all_codes:
                    equipment_code = f'EQP-{code}-TORY20'
                    if code in visible_codes:
                        self.assertIn(equipment_code, response)
                    else:
                        self.assertNotIn(equipment_code, response)

    def test_inventory_brasil_admin_never_sees_unrelated_company(self):
        response = self._ask_equipment_question(
            self.admin_brasil,
            context={
                'intencao': 'equipamentos',
                'base': self.bases['ANTROPIC'].nome,
            },
        )

        self.assertIn('EQP-BR-TORY20', response)
        self.assertIn('EQP-LATAM-TORY20', response)
        self.assertIn('EQP-OXXO-TORY20', response)
        self.assertNotIn('EQP-ANTROPIC-TORY20', response)
        self.assertNotIn(self.bases['ANTROPIC'].nome, response)

    def test_inventory_brasil_admin_can_filter_authorized_related_company(self):
        response = AssistenteOperacionalService.responder(
            self.admin_brasil,
            'Liste os equipamentos da base LATAM',
            tenant_scope=TenantScope.fresh_for_user(self.admin_brasil),
        )['resposta']

        self.assertIn('EQP-LATAM-TORY20', response)
        self.assertNotIn('EQP-BR-TORY20', response)
        self.assertNotIn('EQP-OXXO-TORY20', response)
        self.assertNotIn('EQP-ANTROPIC-TORY20', response)

    def test_scope_from_another_identity_is_rejected(self):
        foreign_scope = TenantScope.fresh_for_user(self.admin_brasil)

        with self.assertRaises(PermissionDenied):
            AssistenteOperacionalService.responder(
                self.admin_latam,
                'Liste todos os equipamentos cadastrados',
                tenant_scope=foreign_scope,
            )

    def test_forged_platform_scope_is_rejected_for_tenant_admin(self):
        forged_scope = TenantScope(
            user_id=self.admin_latam.pk,
            is_platform_scope=True,
        )

        with self.assertRaises(PermissionDenied):
            AssistenteOperacionalService.responder(
                self.admin_latam,
                'Liste todos os equipamentos cadastrados',
                tenant_scope=forged_scope,
            )

    def test_prices_and_requests_remain_inside_primary_tenant(self):
        category = CategoriaInsumo.objects.create(nome='Categoria Tory 20')
        supply = Insumo.objects.create(
            descricao='Papel Tory 20',
            categoria=category,
            unidade_medida='PCT',
        )
        supplier_br = FornecedorInsumo.objects.create(
            nome='Fornecedor BR Tory20',
            documento='11111111000191',
        )
        supplier_antropic = FornecedorInsumo.objects.create(
            nome='Fornecedor Antropic Tory20',
            documento='22222222000191',
        )
        PrecoFornecedorInsumo.objects.create(
            empresa=self.brasil,
            insumo=supply,
            fornecedor=supplier_br,
            valor_unitario=Decimal('15.00'),
            cadastrado_por=self.admin_brasil,
        )
        PrecoFornecedorInsumo.objects.create(
            empresa=self.antropic,
            insumo=supply,
            fornecedor=supplier_antropic,
            valor_unitario=Decimal('1.00'),
            cadastrado_por=self.admin_brasil,
        )
        SolicitacaoInsumo.objects.create(
            protocolo='SOL-BR-TORY20',
            base=self.bases['BR'],
            solicitante=self.admin_brasil,
        )
        SolicitacaoInsumo.objects.create(
            protocolo='SOL-ANTROPIC-TORY20',
            base=self.bases['ANTROPIC'],
            solicitante=self.admin_brasil,
        )
        scope = TenantScope.fresh_for_user(self.admin_brasil)

        prices = AssistenteOperacionalService.responder(
            self.admin_brasil,
            'Compare preços do insumo Papel Tory 20',
            tenant_scope=scope,
        )['resposta']
        requests = AssistenteOperacionalService.responder(
            self.admin_brasil,
            'Mostre as solicitações de insumos',
            tenant_scope=scope,
        )['resposta']

        self.assertIn(supplier_br.nome, prices)
        self.assertNotIn(supplier_antropic.nome, prices)
        self.assertIn('SOL-BR-TORY20', requests)
        self.assertNotIn('SOL-ANTROPIC-TORY20', requests)

    def test_transfer_counts_do_not_include_unrelated_tenant(self):
        destination_br = Base.objects.create(
            nome='DESTINO BR TORY20', empresa=self.brasil
        )
        destination_antropic = Base.objects.create(
            nome='DESTINO ANTROPIC TORY20', empresa=self.antropic
        )
        Transferencia.objects.create(
            protocolo='TRF-BR-TORY20',
            solicitado_por=self.admin_brasil,
            regional_origem=self.bases['BR'],
            regional_destino=destination_br,
        )
        Transferencia.objects.create(
            protocolo='TRF-ANTROPIC-TORY20',
            solicitado_por=self.admin_brasil,
            regional_origem=self.bases['ANTROPIC'],
            regional_destino=destination_antropic,
        )

        response = AssistenteOperacionalService.responder(
            self.admin_brasil,
            'Quantas transferências estão visíveis em todas as bases?',
            tenant_scope=TenantScope.fresh_for_user(self.admin_brasil),
        )['resposta']

        self.assertIn('1 transferencia(s) visiveis', response)
