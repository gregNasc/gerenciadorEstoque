from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from estoque.models import (
    Base,
    CapacidadeRelacionamentoEmpresa,
    Empresa,
    Emprestimo,
    Equipamento,
    GrupoRegional,
    Perfil,
    Produto,
    RelacionamentoEmpresa,
    Sick,
    Transferencia,
)
from estoque.policies.compras import GruposCorporativos
from estoque.policies.tenant_operations import TenantOperationPolicy


class TenantOperationsStage14Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brasil = Empresa.objects.create(nome='Inventory Brasil Etapa 14')
        cls.latam = Empresa.objects.create(nome='Inventory LATAM Etapa 14')
        cls.externa = Empresa.objects.create(nome='Externa Etapa 14')
        cls.grupo = GrupoRegional.objects.create(nome='Grupo Etapa 14')
        cls.base_brasil = Base.objects.create(
            nome='Base Brasil Etapa 14', empresa=cls.brasil,
            grupo_regional=cls.grupo,
        )
        cls.base_latam = Base.objects.create(
            nome='Base LATAM Etapa 14', empresa=cls.latam,
            grupo_regional=cls.grupo,
        )
        cls.base_externa = Base.objects.create(
            nome='Base Externa Etapa 14', empresa=cls.externa,
            grupo_regional=cls.grupo,
        )
        cls.produto = Produto.objects.create(
            codigo='PROD-ETAPA14', descricao='Produto Etapa 14',
            fabricante='Inventory', modelo='Tenant', categoria='Coletores',
        )
        cls.equipamentos = {
            base.pk: Equipamento.objects.create(
                produto=cls.produto,
                numero_serie=f'SERIE-E14-{base.pk}',
                patrimonio=f'PAT-E14-{base.pk}',
                codigo=f'EQP-E14-{base.pk}',
                regional=base,
                status='ATIVO',
            )
            for base in (cls.base_brasil, cls.base_latam, cls.base_externa)
        }
        cls.admin = User.objects.create_user('admin.etapa14', password='SenhaTeste123!')
        cls.admin.perfil.role = Perfil.Role.ADMIN
        cls.admin.perfil.empresa = cls.brasil
        cls.admin.perfil.save()
        cls.admin.perfil.empresas_acesso_adicional.add(cls.latam)

        cls.operador = User.objects.create_user('operador.etapa14', password='SenhaTeste123!')
        cls.operador.perfil.role = Perfil.Role.OPERADOR
        cls.operador.perfil.empresa = cls.brasil
        cls.operador.perfil.save()
        cls.operador.perfil.regionais.add(cls.base_brasil)

        cls.relacao = RelacionamentoEmpresa.objects.create(
            empresa_origem=cls.brasil,
            empresa_destino=cls.latam,
        )
        for resource in ('SICK', 'TRANSFERENCIAS', 'EMPRESTIMOS'):
            for action in ('VISUALIZAR', 'MOVIMENTAR', 'APROVAR'):
                CapacidadeRelacionamentoEmpresa.objects.create(
                    relacionamento=cls.relacao,
                    recurso=resource,
                    acao=action,
                )

        cls.transferencia_valida = Transferencia.objects.create(
            protocolo='TRA-E14-VALIDA', solicitado_por=cls.admin,
            regional_origem=cls.base_brasil,
            regional_destino=cls.base_latam,
        )
        cls.transferencia_forjada = Transferencia.objects.create(
            protocolo='TRA-E14-FORJADA', solicitado_por=cls.admin,
            regional_origem=cls.base_brasil,
            regional_destino=cls.base_externa,
        )
        cls.emprestimo_valido = Emprestimo.objects.create(
            protocolo='EMP-E14-VALIDO', grupo=cls.grupo,
            regional_origem=cls.base_brasil,
            regional_destino=cls.base_latam,
            solicitado_por=cls.admin,
            motivo='Teste Etapa 14', data_emprestimo=timezone.localdate(),
            data_prevista_devolucao=timezone.localdate() + timedelta(days=7),
        )
        cls.emprestimo_forjado = Emprestimo.objects.create(
            protocolo='EMP-E14-FORJADO', grupo=cls.grupo,
            regional_origem=cls.base_brasil,
            regional_destino=cls.base_externa,
            solicitado_por=cls.admin,
            motivo='Teste de isolamento', data_emprestimo=timezone.localdate(),
            data_prevista_devolucao=timezone.localdate() + timedelta(days=7),
        )

    def test_cross_company_operation_needs_exact_movement_capability(self):
        visible = set(TenantOperationPolicy.transferencias(
            self.admin
        ).values_list('pk', flat=True))
        self.assertEqual(visible, {self.transferencia_valida.pk})

        self.relacao.capacidades.filter(
            recurso='TRANSFERENCIAS', acao='MOVIMENTAR'
        ).update(ativo=False)
        self.assertFalse(
            TenantOperationPolicy.transferencias(self.admin).exists()
        )

    def test_cross_company_flow_requires_directional_movement_capability(self):
        self.assertTrue(TenantOperationPolicy.flow_allowed(
            self.base_brasil, self.base_latam, 'TRANSFERENCIAS'
        ))
        self.assertFalse(TenantOperationPolicy.flow_allowed(
            self.base_latam, self.base_brasil, 'TRANSFERENCIAS'
        ))
        self.assertFalse(TenantOperationPolicy.flow_allowed(
            self.base_brasil, self.base_externa, 'TRANSFERENCIAS'
        ))
        with self.assertRaises(PermissionDenied):
            TenantOperationPolicy.require_flow(
                self.admin, self.base_brasil, self.base_externa, 'TRANSFERENCIAS'
            )

    def test_manager_and_operator_remain_bound_to_assigned_bases(self):
        visible = set(TenantOperationPolicy.transferencias(
            self.operador
        ).values_list('pk', flat=True))
        self.assertEqual(visible, {self.transferencia_valida.pk})
        self.assertFalse(TenantOperationPolicy.can_access_base(
            self.operador, self.base_latam, 'TRANSFERENCIAS', 'MOVIMENTAR'
        ))

    def test_sick_maintenance_group_does_not_become_cross_tenant(self):
        self.operador.groups.add(Group.objects.get_or_create(
            name=GruposCorporativos.SICK_MANUTENCAO
        )[0])
        sick_brasil = Sick.objects.create(
            equipamento=self.equipamentos[self.base_brasil.pk],
            base_origem=self.base_brasil, categoria='HARDWARE', motivo='Teste',
            tipo_destino=Sick.TipoDestino.MATRIZ,
        )
        Sick.objects.create(
            equipamento=self.equipamentos[self.base_externa.pk],
            base_origem=self.base_externa, categoria='HARDWARE', motivo='Teste',
            tipo_destino=Sick.TipoDestino.MATRIZ,
        )

        self.assertEqual(
            set(TenantOperationPolicy.sick(self.operador).values_list('pk', flat=True)),
            {sick_brasil.pk},
        )

    def test_forged_operation_ids_return_404(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse(
            'estoque:detalhe_emprestimo', args=[self.emprestimo_forjado.pk]
        )).status_code, 404)
        self.assertEqual(self.client.get(reverse(
            'estoque:transferencia_selecionados', args=[self.transferencia_forjada.pk]
        )).status_code, 404)

    def test_related_loan_is_visible_but_external_is_not(self):
        visible = set(TenantOperationPolicy.emprestimos(
            self.admin
        ).values_list('pk', flat=True))
        self.assertEqual(visible, {self.emprestimo_valido.pk})
