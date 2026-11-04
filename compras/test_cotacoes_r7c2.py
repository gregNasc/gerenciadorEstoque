from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from compras.models import (
    Aquisicao,
    CotacaoFornecedor,
    EventoCompra,
    FornecedorEmpresa,
    ItemAquisicao,
    ItemCotacaoFornecedor,
    ProcessoCotacao,
)
from compras.services import (
    AquisicaoService,
    CotacaoService,
    FornecedorEmpresaService,
)
from estoque.models import Base, Empresa, Perfil
from insumos.models import (
    CategoriaInsumo,
    EventoSolicitacaoInsumo,
    FornecedorInsumo,
    Insumo,
    ItemSolicitacaoInsumo,
    SolicitacaoInsumo,
)
from insumos.constants import GruposInsumos


class CotacoesPersistentesR7C2Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa_a = Empresa.objects.create(nome='Empresa Cotação A')
        cls.empresa_b = Empresa.objects.create(nome='Empresa Cotação B')
        cls.base_a = Base.objects.create(nome='BASE COTAÇÃO A', empresa=cls.empresa_a)
        cls.base_b = Base.objects.create(nome='BASE COTAÇÃO B', empresa=cls.empresa_b)
        cls.admin_a = cls._admin('admin.cotacao.a', cls.empresa_a)
        cls.admin_b = cls._admin('admin.cotacao.b', cls.empresa_b)
        cls.jose = cls._admin('jose.barboza', cls.empresa_a)
        cls.gestor_a = cls._usuario_base(
            'gestor.cotacao.a', cls.empresa_a, cls.base_a, Perfil.Role.GESTOR,
        )
        cls.compras_a = cls._usuario_base(
            'compras.cotacao.a', cls.empresa_a, cls.base_a, Perfil.Role.OPERADOR,
        )
        grupo_compras, _ = Group.objects.get_or_create(name=GruposInsumos.COMPRAS)
        cls.compras_a.groups.add(grupo_compras)
        categoria = CategoriaInsumo.objects.create(nome='Categoria Cotação')
        cls.insumo = Insumo.objects.create(
            descricao='Material para cotação',
            categoria=categoria,
            unidade_medida='UN',
        )
        cls.solicitacao_a = cls._solicitacao(
            cls.base_a, cls.admin_a, 'INS-COT-A', cls.insumo,
        )
        cls.solicitacao_b = cls._solicitacao(
            cls.base_b, cls.admin_b, 'INS-COT-B', cls.insumo,
        )
        cls.item_a = cls.solicitacao_a.itens.get()
        cls.fornecedor_1 = FornecedorInsumo.objects.create(
            nome='Fornecedor Cotação 1', documento='31000000000101',
        )
        cls.fornecedor_2 = FornecedorInsumo.objects.create(
            nome='Fornecedor Cotação 2', documento='31000000000102',
        )
        cls.fornecedor_pendente = FornecedorInsumo.objects.create(
            nome='Fornecedor Cotação Pendente', documento='31000000000103',
        )
        cls.relacao_1 = cls._relacao_homologada(
            cls.empresa_a, cls.fornecedor_1, cls.admin_a,
        )
        cls.relacao_2 = cls._relacao_homologada(
            cls.empresa_a, cls.fornecedor_2, cls.admin_a,
        )
        cls.relacao_pendente, _ = FornecedorEmpresaService.registrar(
            empresa=cls.empresa_a,
            fornecedor=cls.fornecedor_pendente,
            usuario=cls.admin_a,
        )

    @staticmethod
    def _admin(username, empresa):
        usuario = User.objects.create_user(username, password='Teste123!')
        usuario.perfil.role = Perfil.Role.ADMIN
        usuario.perfil.empresa = empresa
        usuario.perfil.save()
        return usuario

    @staticmethod
    def _usuario_base(username, empresa, base, role):
        usuario = User.objects.create_user(username, password='Teste123!')
        usuario.perfil.role = role
        usuario.perfil.empresa = empresa
        usuario.perfil.save()
        usuario.perfil.regionais.add(base)
        return usuario

    @staticmethod
    def _solicitacao(base, usuario, protocolo, insumo):
        solicitacao = SolicitacaoInsumo.objects.create(
            protocolo=protocolo,
            base=base,
            solicitante=usuario,
            status='EM_ANALISE',
            justificativa='Reposição operacional necessária.',
        )
        ItemSolicitacaoInsumo.objects.create(
            solicitacao=solicitacao,
            tipo=ItemSolicitacaoInsumo.Tipo.INSUMO,
            insumo=insumo,
            quantidade=Decimal('3'),
        )
        return solicitacao

    @staticmethod
    def _relacao_homologada(empresa, fornecedor, usuario):
        relacao, _ = FornecedorEmpresaService.registrar(
            empresa=empresa,
            fornecedor=fornecedor,
            usuario=usuario,
        )
        return FornecedorEmpresaService.alterar_status(
            relacao,
            status=FornecedorEmpresa.Status.HOMOLOGADO,
            usuario=usuario,
        )

    def _proposta(self, processo, relacao, valor):
        return CotacaoService.adicionar_proposta(
            processo=processo,
            fornecedor_empresa=relacao,
            usuario=self.admin_a,
            itens=[{
                'item_solicitacao': self.item_a,
                'quantidade': Decimal('3'),
                'valor_unitario': Decimal(valor),
            }],
            prazo_entrega_dias=5,
            frete=Decimal('10'),
            impostos=Decimal('0'),
            desconto=Decimal('0'),
            condicao_pagamento='30 dias',
        )

    def _cotacao_decidida(self, *, aprovada=False):
        processo, _ = CotacaoService.abrir(
            solicitacao=self.solicitacao_a,
            usuario=self.admin_a,
        )
        proposta = self._proposta(processo, self.relacao_1, '10')
        CotacaoService.decidir(
            processo=processo,
            proposta=proposta,
            usuario=self.admin_a,
            justificativa='Melhor condição geral para atender a operação.',
        )
        if aprovada:
            self.solicitacao_a.status = 'APROVADA'
            self.solicitacao_a.aprovado_por = self.admin_a
            self.solicitacao_a.save(update_fields=['status', 'aprovado_por'])
        processo.refresh_from_db()
        return processo, proposta

    def test_abertura_e_idempotente_e_auditada(self):
        processo, criado = CotacaoService.abrir(
            solicitacao=self.solicitacao_a,
            usuario=self.admin_a,
        )
        repetido, criado_novamente = CotacaoService.abrir(
            solicitacao=self.solicitacao_a,
            usuario=self.admin_a,
        )

        self.assertTrue(criado)
        self.assertFalse(criado_novamente)
        self.assertEqual(processo, repetido)
        self.assertEqual(processo.empresa, self.empresa_a)
        self.assertTrue(EventoSolicitacaoInsumo.objects.filter(
            solicitacao=self.solicitacao_a,
            tipo=EventoSolicitacaoInsumo.Tipo.COTACAO_ABERTA,
        ).exists())

    def test_proposta_exige_fornecedor_homologado(self):
        processo, _ = CotacaoService.abrir(
            solicitacao=self.solicitacao_a,
            usuario=self.admin_a,
        )
        with self.assertRaisesMessage(
            ValidationError, 'Selecione um fornecedor homologado e ativo.',
        ):
            CotacaoService.adicionar_proposta(
                processo=processo,
                fornecedor_empresa=self.relacao_pendente,
                usuario=self.admin_a,
                itens=[{
                    'item_solicitacao': self.item_a,
                    'quantidade': Decimal('3'),
                    'valor_unitario': Decimal('20'),
                }],
            )
        self.assertFalse(CotacaoFornecedor.objects.filter(
            processo=processo,
        ).exists())

    def test_item_de_outra_solicitacao_reverte_proposta_inteira(self):
        processo, _ = CotacaoService.abrir(
            solicitacao=self.solicitacao_a,
            usuario=self.admin_a,
        )
        item_estranho = self.solicitacao_b.itens.get()
        with self.assertRaisesMessage(
            ValidationError, 'Um item não pertence à solicitação cotada.',
        ):
            CotacaoService.adicionar_proposta(
                processo=processo,
                fornecedor_empresa=self.relacao_1,
                usuario=self.admin_a,
                itens=[{
                    'item_solicitacao': item_estranho,
                    'quantidade': Decimal('1'),
                    'valor_unitario': Decimal('10'),
                }],
            )
        self.assertFalse(CotacaoFornecedor.objects.filter(
            processo=processo,
        ).exists())
        self.assertFalse(ItemCotacaoFornecedor.objects.exists())

    def test_decisao_pode_escolher_maior_valor_mas_exige_justificativa(self):
        processo, _ = CotacaoService.abrir(
            solicitacao=self.solicitacao_a,
            usuario=self.admin_a,
        )
        menor = self._proposta(processo, self.relacao_1, '10')
        maior = self._proposta(processo, self.relacao_2, '15')
        with self.assertRaisesMessage(
            ValidationError, 'Informe uma justificativa clara',
        ):
            CotacaoService.decidir(
                processo=processo,
                proposta=maior,
                usuario=self.admin_a,
                justificativa='Curta',
            )

        CotacaoService.decidir(
            processo=processo,
            proposta=maior,
            usuario=self.admin_a,
            justificativa='Melhor prazo e condição técnica para a operação.',
        )
        processo.refresh_from_db()
        menor.refresh_from_db()
        maior.refresh_from_db()
        self.assertGreater(maior.valor_total, menor.valor_total)
        self.assertEqual(processo.proposta_escolhida, maior)
        self.assertEqual(maior.status, CotacaoFornecedor.Status.ESCOLHIDA)
        self.assertEqual(
            menor.status, CotacaoFornecedor.Status.NAO_SELECIONADA,
        )
        self.assertTrue(EventoSolicitacaoInsumo.objects.filter(
            solicitacao=self.solicitacao_a,
            tipo=EventoSolicitacaoInsumo.Tipo.COTACAO_DECIDIDA,
        ).exists())

    def test_escopo_de_tenant_e_bloqueio_financeiro(self):
        processo, _ = CotacaoService.abrir(
            solicitacao=self.solicitacao_a,
            usuario=self.admin_a,
        )
        self.assertFalse(CotacaoService.queryset(self.admin_b).filter(
            pk=processo.pk,
        ).exists())
        with self.assertRaises(PermissionDenied):
            CotacaoService.abrir(
                solicitacao=self.solicitacao_a,
                usuario=self.admin_b,
            )
        self.client.force_login(self.admin_b)
        self.assertEqual(self.client.get(reverse(
            'compras:cotacao_solicitacao', args=[self.solicitacao_a.pk],
        )).status_code, 404)
        self.client.force_login(self.jose)
        self.assertEqual(self.client.get(reverse(
            'compras:cotacao_solicitacao', args=[self.solicitacao_a.pk],
        )).status_code, 403)
        self.client.force_login(self.gestor_a)
        self.assertEqual(self.client.get(reverse(
            'compras:cotacao_solicitacao', args=[self.solicitacao_a.pk],
        )).status_code, 403)

    def test_perfil_compras_da_base_pode_operar_cotacao(self):
        self.client.force_login(self.compras_a)
        abertura = self.client.post(reverse(
            'compras:cotacao_solicitacao', args=[self.solicitacao_a.pk],
        ), {'acao': 'abrir'})
        self.assertRedirects(abertura, reverse(
            'compras:cotacao_solicitacao', args=[self.solicitacao_a.pk],
        ))
        self.assertTrue(ProcessoCotacao.objects.filter(
            solicitacao=self.solicitacao_a,
            criado_por=self.compras_a,
        ).exists())

    def test_interface_so_expoe_cotacao_a_usuario_financeiro_autorizado(self):
        self.client.force_login(self.admin_a)
        detalhe = self.client.get(reverse(
            'insumos:detalhe_solicitacao', args=[self.solicitacao_a.pk],
        ))
        self.assertContains(detalhe, 'Abrir cotação')
        abertura = self.client.post(reverse(
            'compras:cotacao_solicitacao', args=[self.solicitacao_a.pk],
        ), {'acao': 'abrir'})
        self.assertRedirects(abertura, reverse(
            'compras:cotacao_solicitacao', args=[self.solicitacao_a.pk],
        ))
        pagina = self.client.get(reverse(
            'compras:cotacao_solicitacao', args=[self.solicitacao_a.pk],
        ))
        self.assertContains(pagina, 'Registrar proposta')
        self.assertContains(pagina, self.fornecedor_1.nome)
        self.assertNotContains(pagina, self.fornecedor_pendente.nome)

    def test_aquisicao_exige_solicitacao_aprovada(self):
        processo, _ = self._cotacao_decidida()
        with self.assertRaisesMessage(
            ValidationError,
            'A solicitação precisa estar aprovada',
        ):
            AquisicaoService.criar_da_cotacao(
                processo=processo,
                usuario=self.admin_a,
            )
        self.assertFalse(Aquisicao.objects.exists())

    def test_geracao_e_idempotente_preserva_origem_base_e_total(self):
        processo, proposta = self._cotacao_decidida(aprovada=True)
        aquisicao, criada = AquisicaoService.criar_da_cotacao(
            processo=processo,
            usuario=self.admin_a,
            numero_pedido_compra='PC-2026-001',
            centro_custo='OPERAÇÃO',
            observacao='Revisar antes da aprovação final.',
        )
        repetida, criada_novamente = AquisicaoService.criar_da_cotacao(
            processo=processo,
            usuario=self.admin_a,
        )

        self.assertTrue(criada)
        self.assertFalse(criada_novamente)
        self.assertEqual(aquisicao, repetida)
        self.assertEqual(Aquisicao.objects.count(), 1)
        self.assertEqual(aquisicao.base_destino, self.base_a)
        self.assertEqual(aquisicao.processo_cotacao, processo)
        self.assertEqual(aquisicao.proposta_origem, proposta)
        self.assertEqual(aquisicao.fornecedor, self.fornecedor_1)
        self.assertEqual(aquisicao.frete_cotacao, Decimal('10'))
        self.assertEqual(aquisicao.valor_total, Decimal('40'))
        item = aquisicao.itens.get()
        self.assertEqual(item.tipo_item, ItemAquisicao.Tipo.INSUMO)
        self.assertEqual(item.insumo, self.insumo)
        self.assertEqual(item.item_cotacao_origem, proposta.itens.get())
        self.assertTrue(EventoCompra.objects.filter(
            aquisicao=aquisicao,
            tipo='AQUISICAO_CRIADA',
            dados__processo_cotacao_id=processo.pk,
        ).exists())

    def test_aprovacao_da_aquisicao_avanca_solicitacao(self):
        processo, _ = self._cotacao_decidida(aprovada=True)
        aquisicao, _ = AquisicaoService.criar_da_cotacao(
            processo=processo,
            usuario=self.admin_a,
        )
        AquisicaoService.aprovar(aquisicao, self.admin_a)

        aquisicao.refresh_from_db()
        self.solicitacao_a.refresh_from_db()
        self.assertEqual(aquisicao.status, Aquisicao.Status.APROVADA)
        self.assertEqual(self.solicitacao_a.status, 'PEDIDO_REALIZADO')
        self.assertIn(
            f'aquisição #{aquisicao.pk} aprovada'.lower(),
            self.solicitacao_a.observacao_aprovacao.lower(),
        )
        self.assertTrue(EventoSolicitacaoInsumo.objects.filter(
            solicitacao=self.solicitacao_a,
            tipo=EventoSolicitacaoInsumo.Tipo.PEDIDO_REALIZADO,
        ).exists())

    def test_interface_exige_confirmacao_e_nao_exibe_termo_tecnico(self):
        processo, _ = self._cotacao_decidida(aprovada=True)
        self.client.force_login(self.admin_a)
        url = reverse(
            'compras:cotacao_solicitacao', args=[self.solicitacao_a.pk],
        )
        pagina = self.client.get(url)
        self.assertContains(pagina, 'Gerar aquisição em rascunho')
        self.assertNotContains(pagina, 'tenant', status_code=200)

        sem_confirmar = self.client.post(url, {'acao': 'gerar_aquisicao'})
        self.assertRedirects(sem_confirmar, url)
        self.assertFalse(Aquisicao.objects.exists())
        confirmada = self.client.post(url, {
            'acao': 'gerar_aquisicao',
            'confirmar_geracao': '1',
            'numero_pedido_compra': 'PC-INTERFACE',
        })
        aquisicao = Aquisicao.objects.get(processo_cotacao=processo)
        self.assertRedirects(confirmada, reverse(
            'compras:aquisicao_detalhe', args=[aquisicao.pk],
        ))

    def test_outro_tenant_e_jose_nao_geram_aquisicao(self):
        processo, _ = self._cotacao_decidida(aprovada=True)
        for usuario in (self.admin_b, self.jose, self.gestor_a):
            with self.subTest(usuario=usuario.username):
                with self.assertRaises(PermissionDenied):
                    AquisicaoService.criar_da_cotacao(
                        processo=processo,
                        usuario=usuario,
                    )
        self.assertFalse(Aquisicao.objects.exists())

