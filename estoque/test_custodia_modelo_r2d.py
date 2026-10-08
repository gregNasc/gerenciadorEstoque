from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import ValidationError
from django.test import TestCase

from estoque.models import (
    Base,
    Colaborador,
    Custodia,
    Empresa,
    LocalFisico,
    Perfil,
    VinculoBaseLocalFisico,
)
from estoque.policies.custodias import CustodiaAccessPolicy


class CustodiaModeloR2DTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa_a = Empresa.objects.create(nome='Empresa Custódia A')
        cls.empresa_b = Empresa.objects.create(nome='Empresa Custódia B')
        cls.base_a = Base.objects.create(nome='Base Custódia A', empresa=cls.empresa_a)
        cls.base_b = Base.objects.create(nome='Base Custódia B', empresa=cls.empresa_b)
        cls.colaborador_a = Colaborador.objects.create(
            empresa=cls.empresa_a,
            base=cls.base_a,
            nome='Colaborador Custódia A',
        )
        cls.colaborador_b = Colaborador.objects.create(
            empresa=cls.empresa_b,
            base=cls.base_b,
            nome='Colaborador Custódia B',
        )
        cls.admin_a = User.objects.create_user('admin.custodia.a')
        Perfil.objects.update_or_create(
            user=cls.admin_a,
            defaults={'empresa': cls.empresa_a, 'role': Perfil.Role.ADMIN},
        )
        cls.admin_b = User.objects.create_user('admin.custodia.b')
        Perfil.objects.update_or_create(
            user=cls.admin_b,
            defaults={'empresa': cls.empresa_b, 'role': Perfil.Role.ADMIN},
        )
        cls.superuser = User.objects.create_superuser(
            'superuser.custodia',
            email='superuser.custodia@example.com',
            password='test-only-password',
        )
        cls.local_a = LocalFisico.objects.create(
            empresa=cls.empresa_a,
            nome='Local Custódia A',
            tipo=LocalFisico.Tipo.ESCRITORIO,
            logradouro='Rua Custódia',
            numero='100',
            bairro='Centro',
            cidade='São Paulo',
            uf='SP',
            cep='01000-000',
        )
        VinculoBaseLocalFisico.objects.create(
            local_fisico=cls.local_a,
            base=cls.base_a,
        )

    def criar_custodia(self, **overrides):
        dados = {
            'empresa': self.empresa_a,
            'colaborador': self.colaborador_a,
            'base': self.base_a,
            'local_fisico': self.local_a,
            'status': Custodia.Status.ATIVA,
            'condicao_geral': Custodia.CondicaoGeral.BOM,
            'observacao': '  Entrega validada  ',
            'registrado_por': self.admin_a,
        }
        dados.update(overrides)
        return Custodia.objects.create(**dados)

    def test_cria_custodia_historica_com_dados_minimos(self):
        custodia = self.criar_custodia()

        self.assertEqual(custodia.empresa, self.empresa_a)
        self.assertEqual(custodia.colaborador, self.colaborador_a)
        self.assertEqual(custodia.base, self.base_a)
        self.assertEqual(custodia.local_fisico, self.local_a)
        self.assertEqual(custodia.observacao, 'ENTREGA VALIDADA')
        self.assertIsNotNone(custodia.criado_em)
        self.assertIsNotNone(custodia.atualizado_em)

    def test_local_fisico_e_opcional(self):
        custodia = self.criar_custodia(local_fisico=None)
        self.assertIsNone(custodia.local_fisico)

    def test_colaborador_de_outra_empresa_e_rejeitado(self):
        with self.assertRaises(ValidationError) as contexto:
            self.criar_custodia(colaborador=self.colaborador_b)
        self.assertIn('colaborador', contexto.exception.message_dict)

    def test_base_de_outra_empresa_e_rejeitada(self):
        with self.assertRaises(ValidationError) as contexto:
            self.criar_custodia(base=self.base_b)
        self.assertIn('base', contexto.exception.message_dict)

    def test_local_precisa_estar_vinculado_a_base(self):
        local_sem_vinculo = LocalFisico.objects.create(
            empresa=self.empresa_a,
            nome='Local sem vínculo',
            tipo=LocalFisico.Tipo.DEPOSITO,
            logradouro='Rua Isolada',
            numero='10',
            bairro='Centro',
            cidade='São Paulo',
            uf='SP',
            cep='01000-001',
        )
        with self.assertRaises(ValidationError) as contexto:
            self.criar_custodia(local_fisico=local_sem_vinculo)
        self.assertIn('local_fisico', contexto.exception.message_dict)

    def test_colaborador_inativo_e_rejeitado(self):
        self.colaborador_a.ativo = False
        self.colaborador_a.save(update_fields=['ativo'])
        with self.assertRaises(ValidationError) as contexto:
            self.criar_custodia()
        self.assertIn('colaborador', contexto.exception.message_dict)

    def test_policy_isola_custodias_por_empresa(self):
        custodia_a = self.criar_custodia()
        custodia_b = self.criar_custodia(
            empresa=self.empresa_b,
            colaborador=self.colaborador_b,
            base=self.base_b,
            local_fisico=None,
            registrado_por=self.admin_b,
        )

        self.assertEqual(
            list(CustodiaAccessPolicy.custodias(self.admin_a)),
            [custodia_a],
        )
        self.assertEqual(
            list(CustodiaAccessPolicy.custodias(self.admin_b)),
            [custodia_b],
        )
        self.assertEqual(
            set(CustodiaAccessPolicy.custodias(self.superuser)),
            {custodia_a, custodia_b},
        )
        self.assertFalse(
            CustodiaAccessPolicy.custodias(AnonymousUser()).exists()
        )

    def test_acao_desconhecida_falha_fechada(self):
        self.criar_custodia()
        self.assertFalse(CustodiaAccessPolicy.custodias(
            self.admin_a,
            action='desconhecida',
        ).exists())
