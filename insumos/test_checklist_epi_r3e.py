from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from estoque.models import Base, Empresa, Perfil
from insumos.models import (
    CategoriaInsumo,
    CertificadoEpi,
    ChecklistDiario,
    Cliente,
    Insumo,
    Inventario,
    ItemChecklist,
    LoteEpi,
    ProdutoEpi,
    VarianteEpi,
)
from insumos.services.checklist_service import ChecklistService


class ChecklistEpiR3ETests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = Empresa.objects.create(nome='Empresa Checklist EPI R3E')
        cls.outra_empresa = Empresa.objects.create(nome='Empresa Oculta EPI R3E')
        cls.base = Base.objects.create(nome='Base Checklist EPI R3E', empresa=cls.empresa)
        cls.outra_base = Base.objects.create(
            nome='Base Oculta EPI R3E', empresa=cls.outra_empresa,
        )
        cls.usuario = User.objects.create_user('admin.checklist.epi.r3e')
        cls.usuario.perfil.empresa = cls.empresa
        cls.usuario.perfil.role = Perfil.Role.ADMIN
        cls.usuario.perfil.save(update_fields=['empresa', 'role'])
        cliente = Cliente.objects.create(sigla='R3E', nome='Cliente R3E')
        inventario = Inventario.objects.create(
            cliente=cliente,
            loja='R3E-01',
            base=cls.base,
            data_inicio=date(2026, 10, 16),
            criado_por=cls.usuario,
        )
        cls.checklist = ChecklistDiario.objects.create(
            inventario=inventario,
            data_inicio=timezone.now(),
            criado_por=cls.usuario,
            responsavel=cls.usuario,
            status='EM_EXECUCAO',
        )
        categoria = CategoriaInsumo.objects.create(nome='Categoria EPI R3E')
        cls.epi = Insumo.objects.create(
            descricao='Bota Checklist R3E',
            categoria=categoria,
            unidade_medida='PAR',
            natureza=Insumo.Natureza.EPI,
            forma_controle=Insumo.FormaControle.LOTE,
        )
        cls.comum = Insumo.objects.create(
            descricao='Papel Checklist R3E',
            categoria=categoria,
            unidade_medida='UN',
        )
        cls.produto = ProdutoEpi.objects.create(
            insumo=cls.epi,
            fabricante_importador='Fabricante R3E',
        )
        cls.certificado = CertificadoEpi.objects.create(
            produto_epi=cls.produto,
            numero_ca='CA-R3E-001',
            validade_ca=date(2027, 12, 31),
        )
        cls.variante = VarianteEpi.objects.create(
            produto_epi=cls.produto,
            nome='Bota Checklist R3E',
            tamanho='39',
        )
        cls.lote = LoteEpi.objects.create(
            base=cls.base,
            produto_epi=cls.produto,
            variante=cls.variante,
            certificado=cls.certificado,
            codigo_lote='LOTE-R3E-VISIVEL',
            validade_fisica=date(2027, 6, 30),
        )
        LoteEpi.objects.create(
            base=cls.outra_base,
            produto_epi=cls.produto,
            variante=cls.variante,
            certificado=cls.certificado,
            codigo_lote='LOTE-R3E-OCULTO',
            validade_fisica=date(2027, 7, 31),
        )

    def test_item_epi_recebe_snapshot_sem_mudar_assinatura_do_fluxo(self):
        item = ChecklistService.adicionar_item(
            checklist=self.checklist,
            insumo=self.epi,
            quantidade_enviada=Decimal('2'),
        )

        self.assertEqual(item.quantidade_enviada, Decimal('2'))
        dados = item.metadados_epi_snapshot
        self.assertEqual(dados['natureza'], Insumo.Natureza.EPI)
        self.assertEqual(dados['base_id'], self.base.pk)
        self.assertEqual(dados['fabricante_importador'], 'FABRICANTE R3E')
        self.assertEqual(dados['certificados'][0]['numero_ca'], 'CA-R3E-001')
        self.assertEqual(dados['lotes'][0]['tamanho_variante'], '39')
        self.assertEqual(dados['lotes'][0]['codigo_lote'], 'LOTE-R3E-VISIVEL')

    def test_snapshot_nao_inclui_lote_de_outra_base(self):
        item = ChecklistService.adicionar_item(
            checklist=self.checklist,
            insumo=self.epi,
            quantidade_enviada=1,
        )

        codigos = {lote['codigo_lote'] for lote in item.metadados_epi_snapshot['lotes']}
        self.assertEqual(codigos, {'LOTE-R3E-VISIVEL'})
        self.assertNotIn('LOTE-R3E-OCULTO', str(item.metadados_epi_snapshot))

    def test_insumo_comum_mantem_snapshot_vazio(self):
        item = ChecklistService.adicionar_item(
            checklist=self.checklist,
            insumo=self.comum,
            quantidade_enviada=1,
        )
        self.assertEqual(item.metadados_epi_snapshot, {})

    def test_snapshot_preserva_ca_historico_apos_edicao(self):
        item = ChecklistService.adicionar_item(
            checklist=self.checklist,
            insumo=self.epi,
            quantidade_enviada=1,
        )
        validade_snapshot = item.metadados_epi_snapshot['certificados'][0]['validade_ca']

        self.certificado.validade_ca = date(2030, 1, 1)
        self.certificado.save(update_fields=['validade_ca', 'atualizado_em'])
        item.refresh_from_db()

        self.assertEqual(validade_snapshot, '2027-12-31')
        self.assertEqual(
            item.metadados_epi_snapshot['certificados'][0]['validade_ca'],
            '2027-12-31',
        )

    def test_criacao_legada_direta_continua_compativel(self):
        item = ItemChecklist.objects.create(
            checklist=self.checklist,
            insumo=self.comum,
            quantidade_enviada=1,
        )
        self.assertEqual(item.metadados_epi_snapshot, {})
