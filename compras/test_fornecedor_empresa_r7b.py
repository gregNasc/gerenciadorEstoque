from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from compras.models import FornecedorEmpresa, ItemAquisicao
from compras.policies import AquisicaoAccessPolicy
from compras.services import AquisicaoService, FornecedorEmpresaService
from estoque.models import Empresa, Perfil
from insumos.models import CategoriaInsumo, FornecedorInsumo, Insumo


class FornecedorEmpresaR7BTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa_a = Empresa.objects.create(nome='Empresa R7B A')
        cls.empresa_b = Empresa.objects.create(nome='Empresa R7B B')
        cls.admin_a = cls._admin('admin.r7b.a', cls.empresa_a)
        cls.admin_b = cls._admin('admin.r7b.b', cls.empresa_b)
        cls.jose = cls._admin('jose.barboza', cls.empresa_a)
        cls.fornecedor = FornecedorInsumo.objects.create(
            nome='Fornecedor canônico R7B',
            documento='28000000000170',
        )
        categoria = CategoriaInsumo.objects.create(nome='Categoria R7B')
        cls.insumo = Insumo.objects.create(
            descricao='Insumo R7B',
            categoria=categoria,
            unidade_medida='UN',
        )

    @staticmethod
    def _admin(username, empresa):
        usuario = User.objects.create_user(username, password='Teste123!')
        usuario.perfil.role = Perfil.Role.ADMIN
        usuario.perfil.empresa = empresa
        usuario.perfil.save()
        return usuario

    def test_mesmo_fornecedor_global_tem_homologacoes_independentes(self):
        relacao_a, criada_a = FornecedorEmpresaService.registrar(
            empresa=self.empresa_a,
            fornecedor=self.fornecedor,
            usuario=self.admin_a,
            codigo_interno='FOR-A',
        )
        relacao_b, criada_b = FornecedorEmpresaService.registrar(
            empresa=self.empresa_b,
            fornecedor=self.fornecedor,
            usuario=self.admin_b,
            codigo_interno='FOR-B',
        )
        FornecedorEmpresaService.alterar_status(
            relacao_a,
            status=FornecedorEmpresa.Status.HOMOLOGADO,
            usuario=self.admin_a,
        )

        self.assertTrue(criada_a)
        self.assertTrue(criada_b)
        self.assertEqual(relacao_a.fornecedor, relacao_b.fornecedor)
        self.assertEqual(
            set(FornecedorEmpresaService.queryset(self.admin_a)),
            {relacao_a},
        )
        self.assertEqual(
            set(FornecedorEmpresaService.queryset(self.admin_b)),
            {relacao_b},
        )
        self.assertEqual(
            set(FornecedorEmpresaService.homologados(
                self.admin_a,
                empresa=self.empresa_a,
            )),
            {relacao_a},
        )
        self.assertFalse(FornecedorEmpresaService.homologados(
            self.admin_b,
            empresa=self.empresa_b,
        ).exists())

    def test_admin_nao_altera_relacao_de_outro_tenant(self):
        relacao_b, _ = FornecedorEmpresaService.registrar(
            empresa=self.empresa_b,
            fornecedor=self.fornecedor,
            usuario=self.admin_b,
        )

        with self.assertRaises(PermissionDenied):
            FornecedorEmpresaService.alterar_status(
                relacao_b,
                status=FornecedorEmpresa.Status.HOMOLOGADO,
                usuario=self.admin_a,
            )

    def test_usuario_restrito_nao_acessa_homologacao_de_fornecedor(self):
        self.assertFalse(
            FornecedorEmpresaService.queryset(self.jose).exists()
        )
        with self.assertRaises(PermissionDenied):
            FornecedorEmpresaService.registrar(
                empresa=self.empresa_a,
                fornecedor=self.fornecedor,
                usuario=self.jose,
            )

    def test_registro_repetido_e_idempotente_e_banco_mantem_unicidade(self):
        relacao, criada = FornecedorEmpresaService.registrar(
            empresa=self.empresa_a,
            fornecedor=self.fornecedor,
            usuario=self.admin_a,
        )
        repetida, criada_novamente = FornecedorEmpresaService.registrar(
            empresa=self.empresa_a,
            fornecedor=self.fornecedor,
            usuario=self.admin_a,
        )

        self.assertTrue(criada)
        self.assertFalse(criada_novamente)
        self.assertEqual(relacao, repetida)
        with self.assertRaises(IntegrityError), transaction.atomic():
            FornecedorEmpresa.objects.create(
                empresa=self.empresa_a,
                fornecedor=self.fornecedor,
                cadastrado_por=self.admin_a,
            )

    def test_relacionamento_nao_armazena_preco_ou_condicao_financeira(self):
        nomes = {campo.name for campo in FornecedorEmpresa._meta.get_fields()}
        self.assertTrue({'empresa', 'fornecedor', 'status'} <= nomes)
        self.assertFalse({
            'preco', 'valor', 'valor_unitario', 'condicoes_pagamento',
        } & nomes)

    def test_fornecedor_canonico_inativo_nao_pode_ser_homologado(self):
        relacao, _ = FornecedorEmpresaService.registrar(
            empresa=self.empresa_a,
            fornecedor=self.fornecedor,
            usuario=self.admin_a,
        )
        self.fornecedor.ativo = False
        self.fornecedor.save(update_fields=['ativo', 'atualizado_em'])

        with self.assertRaisesMessage(
            ValidationError,
            'Um fornecedor inativo não pode ser homologado.',
        ):
            FornecedorEmpresaService.alterar_status(
                relacao,
                status=FornecedorEmpresa.Status.HOMOLOGADO,
                usuario=self.admin_a,
            )

    def test_interface_vincula_por_cnpj_sem_exibir_diretorio_global(self):
        segredo = FornecedorInsumo.objects.create(
            nome='Fornecedor exclusivo tenant B',
            documento='28000000000199',
        )
        FornecedorEmpresaService.registrar(
            empresa=self.empresa_b,
            fornecedor=segredo,
            usuario=self.admin_b,
        )
        self.client.force_login(self.admin_a)

        pagina = self.client.get(reverse('compras:fornecedores_empresa'))
        self.assertEqual(pagina.status_code, 200)
        self.assertNotContains(pagina, segredo.nome)
        resposta = self.client.post(reverse('compras:fornecedores_empresa'), {
            'acao': 'registrar',
            'empresa': self.empresa_a.pk,
            'documento_fornecedor': '28.000.000/0001-70',
            'codigo_interno': 'COD-A',
            'observacao': 'Cadastro por CNPJ exato',
        })
        self.assertRedirects(
            resposta,
            f"{reverse('compras:fornecedores_empresa')}?empresa={self.empresa_a.pk}",
        )
        self.assertTrue(FornecedorEmpresa.objects.filter(
            empresa=self.empresa_a,
            fornecedor=self.fornecedor,
            status=FornecedorEmpresa.Status.PENDENTE,
        ).exists())
        relacionamento = FornecedorEmpresa.objects.get(
            empresa=self.empresa_a,
            fornecedor=self.fornecedor,
        )
        alterar = self.client.post(reverse('compras:fornecedores_empresa'), {
            'acao': 'alterar_status',
            'relacionamento_id': relacionamento.pk,
            'status': FornecedorEmpresa.Status.HOMOLOGADO,
        })
        self.assertRedirects(
            alterar,
            f"{reverse('compras:fornecedores_empresa')}?empresa={self.empresa_a.pk}",
        )
        relacionamento.refresh_from_db()
        self.assertEqual(
            relacionamento.status,
            FornecedorEmpresa.Status.HOMOLOGADO,
        )

    def test_api_e_formulario_listam_apenas_homologados_do_tenant(self):
        relacao_a, _ = FornecedorEmpresaService.registrar(
            empresa=self.empresa_a,
            fornecedor=self.fornecedor,
            usuario=self.admin_a,
        )
        FornecedorEmpresaService.alterar_status(
            relacao_a,
            status=FornecedorEmpresa.Status.HOMOLOGADO,
            usuario=self.admin_a,
        )
        outro = FornecedorInsumo.objects.create(
            nome='Fornecedor API tenant B',
            documento='28000000000200',
        )
        relacao_b, _ = FornecedorEmpresaService.registrar(
            empresa=self.empresa_b,
            fornecedor=outro,
            usuario=self.admin_b,
        )
        FornecedorEmpresaService.alterar_status(
            relacao_b,
            status=FornecedorEmpresa.Status.HOMOLOGADO,
            usuario=self.admin_b,
        )
        self.client.force_login(self.admin_a)

        resposta = self.client.get(
            reverse('compras:api_fornecedores_homologados'),
            {'empresa': self.empresa_a.pk},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            resposta.json()['fornecedores'],
            [{
                'id': self.fornecedor.pk,
                'nome': self.fornecedor.nome,
                'documento': self.fornecedor.cnpj_formatado,
            }],
        )
        self.assertEqual(self.client.get(
            reverse('compras:api_fornecedores_homologados'),
            {'empresa': self.empresa_b.pk},
        ).status_code, 404)
        formulario = self.client.get(reverse('compras:aquisicao_criar'))
        self.assertContains(formulario, self.fornecedor.nome)
        self.assertNotContains(formulario, outro.nome)

    def test_nova_aquisicao_exige_fornecedor_homologado(self):
        relacao, _ = FornecedorEmpresaService.registrar(
            empresa=self.empresa_a,
            fornecedor=self.fornecedor,
            usuario=self.admin_a,
        )
        item = {
            'tipo_item': ItemAquisicao.Tipo.INSUMO,
            'insumo': self.insumo,
            'quantidade': Decimal('1'),
            'valor_unitario': Decimal('10'),
        }
        with self.assertRaisesMessage(
            ValidationError,
            'O fornecedor precisa estar homologado para esta empresa.',
        ):
            AquisicaoService.criar(
                empresa=self.empresa_a,
                fornecedor=self.fornecedor,
                usuario=self.admin_a,
                itens=[item],
            )
        FornecedorEmpresaService.alterar_status(
            relacao,
            status=FornecedorEmpresa.Status.HOMOLOGADO,
            usuario=self.admin_a,
        )
        aquisicao = AquisicaoService.criar(
            empresa=self.empresa_a,
            fornecedor=self.fornecedor,
            usuario=self.admin_a,
            itens=[item],
        )
        self.assertEqual(aquisicao.fornecedor, self.fornecedor)

    def test_usuario_financeiro_restrito_nao_gerencia_aquisicao(self):
        self.assertFalse(AquisicaoAccessPolicy.pode_gerenciar(self.jose))
        self.client.force_login(self.jose)
        self.assertEqual(
            self.client.get(reverse('compras:aquisicao_criar')).status_code,
            403,
        )

