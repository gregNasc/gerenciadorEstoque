from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from estoque.models import Base, Empresa, Equipamento, Perfil, Produto
from insumos.models import (
    ChecklistEquipamentoQuantidade,
    Cliente,
    Inventario,
)
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
            pessoas=3,
        )
        self.produto = Produto.objects.create(
            codigo='COL-CICLO', descricao='Coletor ciclo', fabricante='Zebra',
            modelo='C1', categoria='Coletores',
        )
        self.equipamentos = [
            Equipamento.objects.create(
                produto=self.produto,
                numero_serie=f'SER-CICLO-{indice}',
                patrimonio=f'PAT-CICLO-{indice}',
                regional=self.base,
                codigo=f'EQ-CICLO-{indice}',
            )
            for indice in range(10)
        ]

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

    def test_quantidade_ate_saldo_e_identificacao_parcial(self):
        checklist = ChecklistService.criar(
            inventario=self.inventario, usuario=self.usuario,
        )
        registro = ChecklistService.registrar_envio_equipamentos(
            checklist=checklist, categoria='Coletores', quantidade=8,
            equipamentos=self.equipamentos[:2], usuario=self.usuario,
        )
        self.assertEqual(registro.quantidade_enviada, 8)
        self.assertEqual(registro.quantidade_identificada, 2)
        self.assertEqual(checklist.equipamentos_utilizados.count(), 2)
        self.assertEqual(ChecklistService.saldo_equipamentos_categoria(self.base, 'Coletores'), 2)

    def test_quantidade_acima_do_saldo_e_regra_pessoas_mais_cinco(self):
        checklist = ChecklistService.criar(
            inventario=self.inventario, usuario=self.usuario,
        )
        with self.assertRaises(ValueError):
            ChecklistService.registrar_envio_equipamentos(
                checklist=checklist, categoria='Coletores', quantidade=11,
                equipamentos=[], usuario=self.usuario,
            )
        with self.assertRaises(ValueError):
            ChecklistService.registrar_envio_equipamentos(
                checklist=checklist, categoria='Coletores', quantidade=9,
                equipamentos=[], usuario=self.usuario,
            )

    def test_retorno_divergente_finaliza_e_reabre_sem_duplicar_reserva(self):
        checklist = ChecklistService.criar(
            inventario=self.inventario, usuario=self.usuario,
        )
        registro = ChecklistService.registrar_envio_equipamentos(
            checklist=checklist, categoria='Coletores', quantidade=5,
            equipamentos=[], usuario=self.usuario,
        )
        ChecklistService.atualizar_retorno_equipamentos_quantitativo(
            registro=registro, quantidade=4, usuario=self.usuario,
        )
        ChecklistService.finalizar(checklist=checklist, usuario=self.usuario)
        ChecklistService.reabrir(checklist=checklist, usuario=self.usuario)
        checklist.refresh_from_db()
        registro.refresh_from_db()
        self.assertEqual(checklist.status, 'EM_EXECUCAO')
        self.assertEqual(registro.status_retorno, ChecklistEquipamentoQuantidade.StatusRetorno.PENDENTE)
        self.assertEqual(ChecklistService.saldo_equipamentos_categoria(self.base, 'Coletores'), 5)
