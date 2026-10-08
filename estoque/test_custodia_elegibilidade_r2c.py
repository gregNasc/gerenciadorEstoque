from django.contrib.auth.models import User
from django.test import TestCase

from compras.models import (
    CapacidadeCatalogoProdutoEmpresa,
    CatalogoProdutoEmpresa,
)
from estoque.models import Base, Empresa, Equipamento, LinhaMovel, OperadoraMovel, Produto
from estoque.services.custodia_elegibilidade_service import CustodiaElegibilidadeService


class CustodiaElegibilidadeR2CTests(TestCase):
    def setUp(self):
        self.empresa_a = Empresa.objects.create(nome='Empresa A', ativa=True)
        self.empresa_b = Empresa.objects.create(nome='Empresa B', ativa=True)
        self.usuario = User.objects.create_user(username='admin-r2c')
        self.base_a = Base.objects.create(nome='Base A', empresa=self.empresa_a)
        self.base_b = Base.objects.create(nome='Base B', empresa=self.empresa_b)
        self.produto = Produto.objects.create(
            codigo='NOTEBOOK-R2C',
            descricao='Notebook R2C',
            fabricante='Teste',
            modelo='R2C',
            categoria='Notebook',
        )
        self.catalogo_a = CatalogoProdutoEmpresa.objects.create(
            empresa=self.empresa_a,
            produto=self.produto,
            ativo=True,
        )
        self.catalogo_b = CatalogoProdutoEmpresa.objects.create(
            empresa=self.empresa_b,
            produto=self.produto,
            ativo=True,
        )
        self.equipamento_a = Equipamento.objects.create(
            produto=self.produto,
            numero_serie='SERIE-R2C-A',
            patrimonio='PATRIMONIO-R2C-A',
            regional=self.base_a,
            codigo='EQ-R2C-A',
        )
        self.equipamento_b = Equipamento.objects.create(
            produto=self.produto,
            numero_serie='SERIE-R2C-B',
            patrimonio='PATRIMONIO-R2C-B',
            regional=self.base_b,
            codigo='EQ-R2C-B',
        )

    def habilitar(self, catalogo, codigo, *, ativa=True):
        return CapacidadeCatalogoProdutoEmpresa.objects.create(
            catalogo=catalogo,
            codigo=codigo,
            ativa=ativa,
        )

    def test_equipamento_exige_capacidade_explicita_no_catalogo_da_empresa(self):
        self.assertFalse(CustodiaElegibilidadeService.permite(
            empresa=self.empresa_a,
            ativo=self.equipamento_a,
        ))

        self.habilitar(
            self.catalogo_a,
            CapacidadeCatalogoProdutoEmpresa.CUSTODIA_PESSOAL,
        )

        self.assertTrue(CustodiaElegibilidadeService.permite(
            empresa=self.empresa_a,
            ativo=self.equipamento_a,
        ))

    def test_capacidade_de_uma_empresa_nao_vaza_para_outra(self):
        self.habilitar(
            self.catalogo_a,
            CapacidadeCatalogoProdutoEmpresa.CUSTODIA_PESSOAL,
        )

        elegiveis_a = CustodiaElegibilidadeService.equipamentos(empresa=self.empresa_a)
        elegiveis_b = CustodiaElegibilidadeService.equipamentos(empresa=self.empresa_b)

        self.assertQuerySetEqual(elegiveis_a, [self.equipamento_a], ordered=False)
        self.assertFalse(elegiveis_b.exists())
        self.assertNotIn(self.equipamento_b, elegiveis_a)

    def test_catalogo_ou_capacidade_inativos_falham_fechados(self):
        capacidade = self.habilitar(
            self.catalogo_a,
            CapacidadeCatalogoProdutoEmpresa.CUSTODIA_PESSOAL,
            ativa=False,
        )
        self.assertFalse(CustodiaElegibilidadeService.equipamentos(
            empresa=self.empresa_a,
        ).exists())

        capacidade.ativa = True
        capacidade.save(update_fields=['ativa'])
        self.catalogo_a.ativo = False
        self.catalogo_a.save(update_fields=['ativo'])
        self.assertFalse(CustodiaElegibilidadeService.equipamentos(
            empresa=self.empresa_a,
        ).exists())

    def test_produto_sem_capacidade_permanece_inelegivel_independente_do_nome(self):
        balanca = Produto.objects.create(
            codigo='BALANCA-R2C',
            descricao='Balança Toledo',
            fabricante='Teste',
            modelo='30kg',
            categoria='Balança',
        )
        CatalogoProdutoEmpresa.objects.create(
            empresa=self.empresa_a,
            produto=balanca,
            ativo=True,
        )
        equipamento = Equipamento.objects.create(
            produto=balanca,
            numero_serie='SERIE-BALANCA-R2C',
            patrimonio='PATRIMONIO-BALANCA-R2C',
            regional=self.base_a,
            codigo='EQ-BALANCA-R2C',
        )

        self.assertFalse(CustodiaElegibilidadeService.permite(
            empresa=self.empresa_a,
            ativo=equipamento,
        ))

    def test_linha_movel_exige_produto_chip_elegivel_na_mesma_empresa(self):
        operadora = OperadoraMovel.objects.create(
            empresa=self.empresa_a,
            nome='Operadora R2C',
            ativa=True,
        )
        linha = LinhaMovel.objects.create(
            empresa=self.empresa_a,
            base=self.base_a,
            operadora=operadora,
            numero_normalizado='+5511999990000',
            iccid='8955000000000000001',
            criado_por=self.usuario,
        )
        self.habilitar(
            self.catalogo_a,
            CapacidadeCatalogoProdutoEmpresa.ATIVO_LINHA_MOVEL,
        )
        self.assertFalse(CustodiaElegibilidadeService.permite(
            empresa=self.empresa_a,
            ativo=linha,
        ))

        self.habilitar(
            self.catalogo_a,
            CapacidadeCatalogoProdutoEmpresa.CUSTODIA_PESSOAL,
        )
        self.assertTrue(CustodiaElegibilidadeService.permite(
            empresa=self.empresa_a,
            ativo=linha,
        ))
        self.assertFalse(CustodiaElegibilidadeService.permite(
            empresa=self.empresa_b,
            ativo=linha,
        ))

    def test_empresa_invalida_e_tipo_desconhecido_falham_fechados(self):
        self.assertFalse(CustodiaElegibilidadeService.equipamentos(
            empresa=None,
        ).exists())
        self.assertFalse(CustodiaElegibilidadeService.linhas_moveis(
            empresa=True,
        ).exists())
        self.assertFalse(CustodiaElegibilidadeService.permite(
            empresa=self.empresa_a,
            ativo=self.produto,
        ))
