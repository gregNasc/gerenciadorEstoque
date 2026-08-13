from django.contrib.auth.models import User
from django.test import TestCase

from estoque.models import Empresa, Perfil
from estoque.policies.compras import ComprasAccessPolicy
from ordens_servico.models import OrdemServico
from ordens_servico.policies import OrdemServicoAccessPolicy


class OrdemServicoTecnicosEspeciaisTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa Tecnicos O.S.')
        self.admin = User.objects.create_user('admin.tecnicos.os')
        self.admin.perfil.role = Perfil.Role.ADMIN
        self.admin.perfil.save(update_fields=['role'])
        self.rafael = User.objects.create_user('rafael.ribeiro')
        self.jose = User.objects.create_user('jose.barboza')
        for indice, tipo in enumerate(
            [
                OrdemServico.Tipo.SICK,
                OrdemServico.Tipo.TRANSFERENCIA,
                OrdemServico.Tipo.EMPRESTIMO,
                OrdemServico.Tipo.INSUMO,
            ],
            start=1,
        ):
            OrdemServico.objects.create(
                numero=f'OS-2026-{indice:04d}',
                ano=2026,
                tipo=tipo,
                empresa=self.empresa,
                solicitante=self.admin,
                motivo=f'Ordem {tipo}',
            )

    def test_rafael_ve_todas_as_os_sick(self):
        self.assertEqual(
            set(OrdemServicoAccessPolicy.queryset(self.rafael).values_list('tipo', flat=True)),
            {OrdemServico.Tipo.SICK},
        )

    def test_jose_ve_transferencia_emprestimo_sick_e_nunca_precos(self):
        self.assertEqual(
            set(OrdemServicoAccessPolicy.queryset(self.jose).values_list('tipo', flat=True)),
            {
                OrdemServico.Tipo.TRANSFERENCIA,
                OrdemServico.Tipo.EMPRESTIMO,
                OrdemServico.Tipo.SICK,
            },
        )
        self.assertTrue(ComprasAccessPolicy.restrito(self.jose))
        self.assertFalse(ComprasAccessPolicy.pode_visualizar_valores(self.jose))
