from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from compras.models import (
    CapacidadeCatalogoProdutoEmpresa,
    CatalogoProdutoEmpresa,
)
from estoque.models import (
    Base,
    Colaborador,
    Custodia,
    Empresa,
    Equipamento,
    ItemCustodia,
    LinhaMovel,
    OperadoraMovel,
    Produto,
)


class ItensCustodiaR2ETests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = Empresa.objects.create(nome='Empresa Item Custódia')
        cls.outra_empresa = Empresa.objects.create(nome='Outra Empresa Item Custódia')
        cls.base = Base.objects.create(nome='Base Item Custódia', empresa=cls.empresa)
        cls.outra_base = Base.objects.create(
            nome='Outra Base Item Custódia',
            empresa=cls.outra_empresa,
        )
        cls.usuario = User.objects.create_user('admin.item.custodia')
        cls.colaborador = Colaborador.objects.create(
            empresa=cls.empresa,
            base=cls.base,
            nome='Colaborador Item Custódia',
        )
        cls.custodia = Custodia.objects.create(
            empresa=cls.empresa,
            colaborador=cls.colaborador,
            base=cls.base,
            registrado_por=cls.usuario,
            status=Custodia.Status.ATIVA,
        )
        cls.produto = Produto.objects.create(
            codigo='PROD-CUSTODIA-R2E',
            descricao='Notebook Custódia R2E',
            fabricante='Teste',
            modelo='R2E',
            categoria='Notebook',
        )
        cls.catalogo = CatalogoProdutoEmpresa.objects.create(
            empresa=cls.empresa,
            produto=cls.produto,
            ativo=True,
        )
        CapacidadeCatalogoProdutoEmpresa.objects.create(
            catalogo=cls.catalogo,
            codigo=CapacidadeCatalogoProdutoEmpresa.CUSTODIA_PESSOAL,
            ativa=True,
        )
        cls.equipamento = Equipamento.objects.create(
            produto=cls.produto,
            numero_serie='SERIE-CUSTODIA-R2E',
            patrimonio='PATRIMONIO-CUSTODIA-R2E',
            regional=cls.base,
            codigo='EQ-CUSTODIA-R2E',
        )
        cls.operadora = OperadoraMovel.objects.create(
            empresa=cls.empresa,
            nome='Operadora Custódia R2E',
            codigo='operadora-custodia-r2e',
        )
        cls.linha = LinhaMovel.objects.create(
            empresa=cls.empresa,
            base=cls.base,
            numero_normalizado='+5511999992000',
            operadora=cls.operadora,
            iccid='89550000000000002000',
            criado_por=cls.usuario,
        )
        cls.produto_chip = Produto.objects.create(
            codigo='CHIP-CUSTODIA-R2E',
            descricao='Chip Custódia R2E',
            fabricante='Teste',
            modelo='SIM',
            categoria='Chip',
        )
        cls.catalogo_chip = CatalogoProdutoEmpresa.objects.create(
            empresa=cls.empresa,
            produto=cls.produto_chip,
            ativo=True,
        )
        for codigo in (
            CapacidadeCatalogoProdutoEmpresa.ATIVO_LINHA_MOVEL,
            CapacidadeCatalogoProdutoEmpresa.CUSTODIA_PESSOAL,
        ):
            CapacidadeCatalogoProdutoEmpresa.objects.create(
                catalogo=cls.catalogo_chip,
                codigo=codigo,
                ativa=True,
            )

    def test_custodia_aceita_multiplos_itens_individualizados(self):
        equipamento = ItemCustodia.objects.create(
            custodia=self.custodia,
            equipamento=self.equipamento,
            condicao_entrega=Custodia.CondicaoGeral.BOM,
        )
        linha = ItemCustodia.objects.create(
            custodia=self.custodia,
            linha_movel=self.linha,
            condicao_entrega=Custodia.CondicaoGeral.NOVO,
        )

        self.assertEqual(list(self.custodia.itens.all()), [equipamento, linha])

    def test_item_exige_exatamente_um_tipo_de_ativo(self):
        with self.assertRaises(ValidationError):
            ItemCustodia.objects.create(custodia=self.custodia)
        with self.assertRaises(ValidationError):
            ItemCustodia.objects.create(
                custodia=self.custodia,
                equipamento=self.equipamento,
                linha_movel=self.linha,
            )

    def test_equipamento_precisa_ser_elegivel(self):
        outro_produto = Produto.objects.create(
            codigo='INELEGIVEL-CUSTODIA-R2E',
            descricao='Ativo inelegível',
            fabricante='Teste',
            modelo='R2E',
            categoria='Outro',
        )
        CatalogoProdutoEmpresa.objects.create(
            empresa=self.empresa,
            produto=outro_produto,
            ativo=True,
        )
        inelegivel = Equipamento.objects.create(
            produto=outro_produto,
            numero_serie='SERIE-INELEGIVEL-R2E',
            patrimonio='PATRIMONIO-INELEGIVEL-R2E',
            regional=self.base,
            codigo='EQ-INELEGIVEL-R2E',
        )
        with self.assertRaises(ValidationError) as contexto:
            ItemCustodia.objects.create(
                custodia=self.custodia,
                equipamento=inelegivel,
            )
        self.assertIn('equipamento', contexto.exception.message_dict)

    def test_ativo_de_outra_empresa_e_rejeitado(self):
        equipamento = Equipamento.objects.create(
            produto=self.produto,
            numero_serie='SERIE-OUTRA-EMPRESA-R2E',
            patrimonio='PATRIMONIO-OUTRA-EMPRESA-R2E',
            regional=self.outra_base,
            codigo='EQ-OUTRA-EMPRESA-R2E',
        )
        with self.assertRaises(ValidationError) as contexto:
            ItemCustodia.objects.create(
                custodia=self.custodia,
                equipamento=equipamento,
            )
        self.assertIn('equipamento', contexto.exception.message_dict)

    def test_ativo_de_outra_base_e_rejeitado(self):
        segunda_base = Base.objects.create(nome='Segunda Base', empresa=self.empresa)
        equipamento = Equipamento.objects.create(
            produto=self.produto,
            numero_serie='SERIE-OUTRA-BASE-R2E',
            patrimonio='PATRIMONIO-OUTRA-BASE-R2E',
            regional=segunda_base,
            codigo='EQ-OUTRA-BASE-R2E',
        )
        with self.assertRaises(ValidationError) as contexto:
            ItemCustodia.objects.create(
                custodia=self.custodia,
                equipamento=equipamento,
            )
        self.assertIn('equipamento', contexto.exception.message_dict)

    def test_snapshots_sao_gerados_dos_dados_reais(self):
        equipamento = ItemCustodia.objects.create(
            custodia=self.custodia,
            equipamento=self.equipamento,
        )
        linha = ItemCustodia.objects.create(
            custodia=self.custodia,
            linha_movel=self.linha,
        )

        self.assertEqual(equipamento.descricao_snapshot, self.produto.descricao)
        self.assertEqual(equipamento.patrimonio_snapshot, self.equipamento.patrimonio)
        self.assertEqual(equipamento.numero_serie_snapshot, self.equipamento.numero_serie)
        self.assertEqual(linha.telefone_snapshot, self.linha.numero_normalizado)
        self.assertEqual(linha.iccid_snapshot, self.linha.iccid)
        self.assertEqual(linha.operadora_snapshot, self.operadora.nome)

    def test_snapshot_nao_muda_quando_ativo_e_editado(self):
        item = ItemCustodia.objects.create(
            custodia=self.custodia,
            equipamento=self.equipamento,
        )
        self.equipamento.patrimonio = 'PATRIMONIO-ALTERADO-R2E'
        self.equipamento.save(update_fields=['patrimonio'])
        item.refresh_from_db()

        self.assertEqual(item.patrimonio_snapshot, 'PATRIMONIO-CUSTODIA-R2E')

    def test_referencia_do_item_historico_e_imutavel(self):
        item = ItemCustodia.objects.create(
            custodia=self.custodia,
            equipamento=self.equipamento,
        )
        item.equipamento = None
        item.linha_movel = self.linha
        with self.assertRaises(ValidationError):
            item.save()

    def test_mesmo_ativo_nao_se_repete_na_mesma_custodia(self):
        ItemCustodia.objects.create(
            custodia=self.custodia,
            equipamento=self.equipamento,
        )
        with self.assertRaises(ValidationError):
            ItemCustodia.objects.create(
                custodia=self.custodia,
                equipamento=self.equipamento,
            )
