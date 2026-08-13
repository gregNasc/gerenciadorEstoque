from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from estoque.models import Base, Empresa, Perfil
from insumos.models import Cliente, Inventario
from insumos.services.checklist_service import ChecklistService


class ChecklistLifecycleTests(TestCase):
    def setUp(self):
        empresa = Empresa.objects.create(nome='Empresa Ciclo Checklist')
        self.base = Base.objects.create(empresa=empresa, nome='Base Ciclo Checklist')
        self.usuario = User.objects.create_user('admin.checklist.ciclo')
        self.usuario.perfil.role = Perfil.Role.ADMIN
        self.usuario.perfil.save(update_fields=['role'])
        cliente = Cliente.objects.create(sigla='CIC', nome='Cliente Ciclo')
        self.inventario = Inventario.objects.create(
            cliente=cliente,
            loja='100',
            base=self.base,
            data_inicio=timezone.localdate(),
            status='PLANEJADO',
            criado_por=self.usuario,
        )

    def test_criar_inicia_inventario_e_finalizar_conclui_ambos(self):
        checklist = ChecklistService.criar(
            inventario=self.inventario,
            usuario=self.usuario,
        )
        self.inventario.refresh_from_db()
        self.assertEqual(checklist.status, 'EM_EXECUCAO')
        self.assertEqual(self.inventario.status, 'EM_ANDAMENTO')
        self.assertIsNotNone(self.inventario.inicio_real)

        ChecklistService.finalizar(checklist=checklist, usuario=self.usuario)
        checklist.refresh_from_db()
        self.inventario.refresh_from_db()
        self.assertEqual(checklist.status, 'FINALIZADO')
        self.assertEqual(self.inventario.status, 'FINALIZADO')
        self.assertIsNotNone(self.inventario.fim_real)
        self.assertEqual(self.inventario.data_fim, timezone.localdate())
