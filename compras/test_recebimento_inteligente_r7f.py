from decimal import Decimal
import uuid

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from compras.models import (
    Aquisicao,
    CatalogoProdutoEmpresa,
    DivergenciaRecebimentoCompra,
    EventoCompra,
    FornecedorEmpresa,
    ItemAquisicao,
    ItemNotaFiscalAquisicao,
    NotaFiscalAquisicao,
    RemessaCompra,
)
from compras.services import AquisicaoService, RemessaCompraService
from estoque.models import Base, Empresa, Equipamento, Perfil, Produto
from insumos.models import FornecedorInsumo


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class RecebimentoInteligenteR7FTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa Recebimento R7F')
        self.base = Base.objects.create(nome='Base Recebimento R7F', empresa=self.empresa)
        self.admin = self._usuario('admin.r7f', Perfil.Role.ADMIN)
        self.gestor = self._usuario('gestor.r7f', Perfil.Role.GESTOR, self.base)
        self.fornecedor = FornecedorInsumo.objects.create(
            nome='Fornecedor R7F', documento='77223344000188',
        )
        FornecedorEmpresa.objects.create(
            empresa=self.empresa,
            fornecedor=self.fornecedor,
            status=FornecedorEmpresa.Status.HOMOLOGADO,
            cadastrado_por=self.admin,
            homologado_por=self.admin,
        )
        self.produto = Produto.objects.create(
            codigo='COLETOR-R7F', descricao='Coletor R7F', fabricante='Fabricante',
            modelo='Modelo R7F', categoria='Coletores',
        )
        CatalogoProdutoEmpresa.objects.create(
            empresa=self.empresa,
            produto=self.produto,
            configurado_por=self.admin,
        )

    def _usuario(self, username, role, base=None):
        usuario = User.objects.create_user(username, password='Teste123!')
        usuario.perfil.empresa = self.empresa
        usuario.perfil.role = role
        usuario.perfil.save()
        if base:
            usuario.perfil.regionais.add(base)
        return usuario

    def _aquisicao_com_nfe(self, quantidade=Decimal('3')):
        aquisicao = AquisicaoService.criar(
            empresa=self.empresa,
            fornecedor=self.fornecedor,
            usuario=self.admin,
            numero_documento='NF-R7F-1',
            itens=[{
                'tipo_item': ItemAquisicao.Tipo.EQUIPAMENTO,
                'produto': self.produto,
                'quantidade': quantidade,
                'valor_unitario': Decimal('1000'),
            }],
        )
        AquisicaoService.aprovar(aquisicao, self.admin)
        nota = NotaFiscalAquisicao.objects.create(
            aquisicao=aquisicao,
            chave_acesso='1' * 44,
            numero='1001',
            hash_xml='a' * 64,
            processado_por=self.admin,
        )
        item_nfe = ItemNotaFiscalAquisicao.objects.create(
            nota_fiscal=nota,
            numero_item=1,
            descricao='Coletor R7F',
            unidade='UN',
            quantidade=quantidade,
            valor_unitario=Decimal('1000'),
            valor_total=quantidade * Decimal('1000'),
            status_catalogo=ItemNotaFiscalAquisicao.StatusCatalogo.CONFIRMADO,
            produto_catalogo=self.produto,
            resolvido_por=self.admin,
        )
        return aquisicao, aquisicao.itens.get(), item_nfe

    def _remessa(self, quantidade=Decimal('3')):
        aquisicao, item_aquisicao, item_nfe = self._aquisicao_com_nfe(quantidade)
        remessa = RemessaCompraService.criar(
            empresa=self.empresa,
            fluxo=RemessaCompra.Fluxo.FORNECEDOR_DIRETO,
            aquisicao=aquisicao,
            base_destino=self.base,
            usuario=self.admin,
            itens=[{
                'item_aquisicao': item_aquisicao,
                'item_nfe': item_nfe,
                'produto': self.produto,
                'quantidade_prevista': quantidade,
                'custo_unitario_snapshot': Decimal('1000'),
            }],
        )
        RemessaCompraService.enviar(remessa, self.admin)
        return remessa

    def test_modelo_recebido_nao_cria_ativo_antes_da_individualizacao(self):
        remessa = self._remessa(Decimal('3'))
        item = remessa.itens.get()
        self.assertEqual(item.produto_id, self.produto.pk)
        self.assertEqual(item.descricao_exibicao, item.produto.descricao)

        self.client.force_login(self.admin)
        tela = self.client.get(reverse('compras:remessa_detalhe', args=[remessa.pk]))
        self.assertEqual(tela.status_code, 200)
        self.assertContains(tela, 'Comparação do recebimento')
        self.assertContains(tela, item.descricao_exibicao)

        recebimento = RemessaCompraService.confirmar(
            remessa=remessa,
            usuario=self.gestor,
            idempotency_key=uuid.uuid4(),
            linhas=[{'item_id': item.pk, 'quantidade_recebida': 3}],
            finalizar=True,
        )

        remessa.refresh_from_db()
        remessa.aquisicao.refresh_from_db()
        linha = recebimento.linhas.get()
        self.assertEqual(remessa.status, RemessaCompra.Status.RECEBIDA)
        self.assertEqual(remessa.aquisicao.status, Aquisicao.Status.RECEBIDA)
        self.assertEqual(linha.quantidade_esperada_aquisicao, Decimal('3'))
        self.assertEqual(linha.quantidade_esperada_nfe, Decimal('3'))
        self.assertEqual(Equipamento.objects.filter(produto=self.produto).count(), 0)

    def test_falta_mantem_remessa_parcial_e_permite_nova_entrega(self):
        remessa = self._remessa(Decimal('3'))
        item = remessa.itens.get()

        recebimento = RemessaCompraService.confirmar(
            remessa=remessa,
            usuario=self.gestor,
            idempotency_key=uuid.uuid4(),
            linhas=[{
                'item_id': item.pk,
                'quantidade_recebida': 2,
                'quantidade_faltante': 1,
            }],
            finalizar=True,
        )

        remessa.refresh_from_db()
        remessa.aquisicao.refresh_from_db()
        self.assertEqual(remessa.status, RemessaCompra.Status.RECEBIDA_PARCIAL)
        self.assertEqual(remessa.aquisicao.status, Aquisicao.Status.EM_RECEBIMENTO)
        self.assertTrue(recebimento.divergencias.filter(
            tipo=DivergenciaRecebimentoCompra.Tipo.FALTA,
        ).exists())

    def test_avaria_e_item_inesperado_encerram_com_divergencia_auditavel(self):
        remessa = self._remessa(Decimal('3'))
        item = remessa.itens.get()

        recebimento = RemessaCompraService.confirmar(
            remessa=remessa,
            usuario=self.gestor,
            idempotency_key=uuid.uuid4(),
            linhas=[{
                'item_id': item.pk,
                'quantidade_recebida': 2,
                'quantidade_avariada': 1,
                'observacao': 'Caixa amassada',
            }],
            item_inesperado={
                'descricao': 'Carregador não previsto',
                'quantidade': 1,
                'observacao': 'Separado para análise',
            },
            finalizar=True,
        )

        remessa.refresh_from_db()
        tipos = set(recebimento.divergencias.values_list('tipo', flat=True))
        self.assertEqual(remessa.status, RemessaCompra.Status.RECEBIDA_DIVERGENCIA)
        self.assertIn(DivergenciaRecebimentoCompra.Tipo.AVARIA, tipos)
        self.assertIn(DivergenciaRecebimentoCompra.Tipo.ITEM_INESPERADO, tipos)
        self.assertTrue(EventoCompra.objects.filter(
            remessa=remessa,
            tipo='RECEBIMENTO_DIVERGENTE',
        ).exists())

    def test_item_fiscal_pendente_nao_pode_ser_usado_na_remessa(self):
        aquisicao, item_aquisicao, item_nfe = self._aquisicao_com_nfe(Decimal('1'))
        item_nfe.status_catalogo = ItemNotaFiscalAquisicao.StatusCatalogo.PENDENTE
        item_nfe.save(update_fields=['status_catalogo'])

        with self.assertRaises(ValidationError):
            RemessaCompraService.criar(
                empresa=self.empresa,
                fluxo=RemessaCompra.Fluxo.FORNECEDOR_DIRETO,
                aquisicao=aquisicao,
                base_destino=self.base,
                usuario=self.admin,
                itens=[{
                    'item_aquisicao': item_aquisicao,
                    'item_nfe': item_nfe,
                    'produto': self.produto,
                    'quantidade_prevista': 1,
                }],
            )
