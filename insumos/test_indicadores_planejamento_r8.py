from io import BytesIO
from decimal import Decimal

import openpyxl
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext

from estoque.models import Base, Empresa, Perfil
from insumos.models import (
    CategoriaInsumo,
    ChecklistDiario,
    Cliente,
    ConsumoInsumo,
    Insumo,
    Inventario,
    ItemChecklist,
    ItemSolicitacaoInsumo,
    SaldoInsumoBase,
    SolicitacaoInsumo,
)
from insumos.services.indicadores_planejamento_service import (
    IndicadoresPlanejamentoService,
)


class IndicadoresPlanejamentoR8Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa_a = Empresa.objects.create(nome='Empresa Planejamento A')
        cls.empresa_b = Empresa.objects.create(nome='Empresa Planejamento B')
        cls.base_a = Base.objects.create(nome='Base Planejamento A', empresa=cls.empresa_a)
        cls.base_b = Base.objects.create(nome='Base Planejamento B', empresa=cls.empresa_b)
        cls.categoria = CategoriaInsumo.objects.create(nome='Materiais R8')
        cls.insumo_a = Insumo.objects.create(
            descricao='Material Operacional A',
            categoria=cls.categoria,
            unidade_medida='UN',
        )
        cls.insumo_critico = Insumo.objects.create(
            descricao='Material Crítico A',
            categoria=cls.categoria,
            unidade_medida='UN',
        )
        cls.insumo_b = Insumo.objects.create(
            descricao='Material Sigiloso B',
            categoria=cls.categoria,
            unidade_medida='UN',
        )
        cls.admin_a = User.objects.create_user('r8.admin.a', password='Teste123!')
        cls.admin_a.perfil.role = Perfil.Role.ADMIN
        cls.admin_a.perfil.empresa = cls.empresa_a
        cls.admin_a.perfil.save(update_fields=['role', 'empresa'])
        cls.gestor_a = User.objects.create_user('r8.gestor.a', password='Teste123!')
        cls.gestor_a.perfil.role = Perfil.Role.GESTOR
        cls.gestor_a.perfil.empresa = cls.empresa_a
        cls.gestor_a.perfil.save(update_fields=['role', 'empresa'])
        cls.gestor_a.perfil.regionais.add(cls.base_a)

        solicitacao_a = SolicitacaoInsumo.objects.create(
            protocolo='R8-A-001',
            base=cls.base_a,
            solicitante=cls.admin_a,
            status='FINALIZADA',
        )
        ItemSolicitacaoInsumo.objects.create(
            solicitacao=solicitacao_a,
            tipo=ItemSolicitacaoInsumo.Tipo.INSUMO,
            insumo=cls.insumo_a,
            quantidade=Decimal('10'),
            quantidade_atendida=Decimal('6'),
        )
        solicitacao_critica = SolicitacaoInsumo.objects.create(
            protocolo='R8-A-002',
            base=cls.base_a,
            solicitante=cls.admin_a,
            status='PENDENTE',
        )
        ItemSolicitacaoInsumo.objects.create(
            solicitacao=solicitacao_critica,
            tipo=ItemSolicitacaoInsumo.Tipo.INSUMO,
            insumo=cls.insumo_critico,
            quantidade=Decimal('2'),
        )
        solicitacao_b = SolicitacaoInsumo.objects.create(
            protocolo='R8-B-001',
            base=cls.base_b,
            solicitante=cls.admin_a,
            status='PENDENTE',
        )
        ItemSolicitacaoInsumo.objects.create(
            solicitacao=solicitacao_b,
            tipo=ItemSolicitacaoInsumo.Tipo.INSUMO,
            insumo=cls.insumo_b,
            quantidade=Decimal('999'),
        )
        SaldoInsumoBase.objects.create(
            base=cls.base_a,
            insumo=cls.insumo_a,
            saldo=Decimal('5'),
            saldo_reservado=Decimal('1'),
        )
        SaldoInsumoBase.objects.create(
            base=cls.base_b,
            insumo=cls.insumo_b,
            saldo=Decimal('999'),
        )

        cliente = Cliente.objects.create(sigla='R8', nome='Cliente R8')
        inventario = Inventario.objects.create(
            cliente=cliente,
            loja='001',
            base=cls.base_a,
            data_inicio=timezone.localdate(),
            criado_por=cls.admin_a,
        )
        checklist = ChecklistDiario.objects.create(
            inventario=inventario,
            data_inicio=timezone.now(),
            criado_por=cls.admin_a,
            responsavel=cls.admin_a,
        )
        item_checklist = ItemChecklist.objects.create(
            checklist=checklist,
            insumo=cls.insumo_a,
            quantidade_utilizada=Decimal('4'),
        )
        ConsumoInsumo.objects.create(
            inventario=inventario,
            item_checklist=item_checklist,
            insumo=cls.insumo_a,
            quantidade=Decimal('4'),
            valor_unitario=Decimal('0'),
            valor_total=Decimal('0'),
        )

    def setUp(self):
        self.client.force_login(self.admin_a)

    def test_servico_distingue_solicitado_atendido_consumido_e_estoque(self):
        resultado = IndicadoresPlanejamentoService.gerar(user=self.admin_a)
        itens = {item['insumo_id']: item for item in resultado['itens']}

        material = itens[self.insumo_a.pk]
        self.assertEqual(material['quantidade_solicitada'], Decimal('10'))
        self.assertEqual(material['quantidade_atendida'], Decimal('6'))
        self.assertEqual(material['quantidade_consumida'], Decimal('4'))
        self.assertEqual(material['estoque_disponivel'], Decimal('4'))
        self.assertEqual(material['fonte_demanda'], 'Consumo')
        self.assertNotIn(self.insumo_b.pk, itens)

        critico = itens[self.insumo_critico.pk]
        self.assertEqual(critico['nivel'], 'CRITICO')
        self.assertIn('solicitação aberta', critico['sugestao'])

    def test_resultado_nao_expoe_campos_financeiros(self):
        resultado = IndicadoresPlanejamentoService.gerar(user=self.admin_a)
        chaves = set().union(*(item.keys() for item in resultado['itens']))
        self.assertFalse({'preco', 'custo', 'valor_total', 'valor_unitario'} & chaves)

    def test_consulta_agregada_nao_cresce_por_item(self):
        with CaptureQueriesContext(connection) as consultas:
            IndicadoresPlanejamentoService.gerar(user=self.admin_a)
        self.assertLessEqual(len(consultas), 16)

    def test_dashboard_abre_na_empresa_principal_e_nao_vaza_outra_empresa(self):
        resposta = self.client.get(reverse('insumos:dashboard_planejamento'))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context['filtro_empresa'], str(self.empresa_a.pk))
        self.assertContains(resposta, self.insumo_a.descricao)
        self.assertContains(resposta, self.insumo_critico.descricao)
        self.assertNotContains(resposta, self.insumo_b.descricao)
        self.assertNotContains(resposta, self.empresa_b.nome)
        self.assertContains(resposta, 'Solicitado')
        self.assertContains(resposta, 'Atendido')
        self.assertContains(resposta, 'Consumido')

    def test_empresa_e_base_fora_do_escopo_sao_negadas(self):
        self.assertEqual(
            self.client.get(
                reverse('insumos:dashboard_planejamento'),
                {'empresa': self.empresa_b.pk},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                reverse('insumos:dashboard_planejamento'),
                {'base': self.base_b.pk},
            ).status_code,
            403,
        )

    def test_exportacao_operacional_respeita_escopo_e_nao_contem_precos(self):
        resposta = self.client.get(reverse('insumos:exportar_planejamento'))

        self.assertEqual(resposta.status_code, 200)
        self.assertIn('spreadsheetml', resposta['Content-Type'])
        workbook = openpyxl.load_workbook(BytesIO(resposta.content), data_only=True)
        valores = [
            str(celula.value or '')
            for linha in workbook['Planejamento'].iter_rows()
            for celula in linha
        ]
        texto = ' | '.join(valores)
        self.assertIn(self.insumo_a.descricao, texto)
        self.assertNotIn(self.insumo_b.descricao, texto)
        self.assertNotIn('PREÇO', texto.upper())
        self.assertNotIn('CUSTO', texto.upper())
        self.assertNotIn('VALOR UNITÁRIO', texto.upper())

    def test_rotulos_principais_possuem_traducao_em_espanhol(self):
        with translation.override('es'):
            self.assertEqual(
                gettext('Planejamento de consumo'),
                'Planificación de consumo',
            )
            self.assertEqual(gettext('Estoque disponível'), 'Stock disponible')

    def test_gestor_sem_perfil_funcional_nao_acessa_indicadores(self):
        self.client.force_login(self.gestor_a)
        resposta = self.client.get(reverse('insumos:dashboard_planejamento'))
        self.assertEqual(resposta.status_code, 403)
        with self.assertRaises(PermissionDenied):
            IndicadoresPlanejamentoService.gerar(user=self.gestor_a)
