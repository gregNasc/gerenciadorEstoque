from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import ValidationError
from django.test import TestCase

from estoque.models import (
    Base,
    CapacidadeRelacionamentoEmpresa,
    Empresa,
    EnderecoPostalBase,
    LocalFisico,
    Perfil,
    RelacionamentoEmpresa,
    VinculoBaseLocalFisico,
)
from estoque.policies.locais_fisicos import LocalFisicoAccessPolicy


class LocalFisicoR2BTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa_a = Empresa.objects.create(nome='Empresa Local A')
        cls.empresa_b = Empresa.objects.create(nome='Empresa Local B')
        cls.empresa_c = Empresa.objects.create(nome='Empresa Local C')
        cls.base_a1 = Base.objects.create(nome='Base A1', empresa=cls.empresa_a)
        cls.base_a2 = Base.objects.create(nome='Base A2', empresa=cls.empresa_a)
        cls.base_b = Base.objects.create(nome='Base B', empresa=cls.empresa_b)
        cls.base_c = Base.objects.create(nome='Base C', empresa=cls.empresa_c)

        cls.admin_a = User.objects.create_user('admin.local.a')
        perfil_admin, _ = Perfil.objects.update_or_create(
            user=cls.admin_a,
            defaults={'empresa': cls.empresa_a, 'role': Perfil.Role.ADMIN},
        )
        perfil_admin.empresas_acesso_adicional.add(cls.empresa_b)
        cls.admin_c = User.objects.create_user('admin.local.c')
        Perfil.objects.update_or_create(
            user=cls.admin_c,
            defaults={'empresa': cls.empresa_c, 'role': Perfil.Role.ADMIN},
        )
        cls.superuser = User.objects.create_superuser(
            'superuser.local',
            email='superuser.local@example.com',
            password='test-only-password',
        )

        cls.relacionamento = RelacionamentoEmpresa.objects.create(
            empresa_origem=cls.empresa_a,
            empresa_destino=cls.empresa_b,
            ativo=True,
        )
        CapacidadeRelacionamentoEmpresa.objects.create(
            relacionamento=cls.relacionamento,
            recurso=CapacidadeRelacionamentoEmpresa.Recurso.OPERACAO,
            acao=CapacidadeRelacionamentoEmpresa.Acao.ADMINISTRAR,
            ativo=True,
        )

    def _local(self, **overrides):
        dados = {
            'empresa': self.empresa_a,
            'nome': 'Local Compartilhado',
            'tipo': LocalFisico.Tipo.ESCRITORIO,
            'logradouro': 'Rua Teste',
            'numero': '100',
            'bairro': 'Centro',
            'cidade': 'São Paulo',
            'uf': 'SP',
            'cep': '01000-000',
        }
        dados.update(overrides)
        return LocalFisico.objects.create(**dados)

    def test_multiplas_bases_podem_compartilhar_o_mesmo_local(self):
        local = self._local()
        VinculoBaseLocalFisico.objects.create(local_fisico=local, base=self.base_a1)
        VinculoBaseLocalFisico.objects.create(local_fisico=local, base=self.base_a2)

        self.assertEqual(set(local.bases.all()), {self.base_a1, self.base_a2})

    def test_compartilhamento_entre_empresas_exige_relacionamento_explicito(self):
        local = self._local()
        VinculoBaseLocalFisico.objects.create(local_fisico=local, base=self.base_b)

        with self.assertRaises(ValidationError) as contexto:
            VinculoBaseLocalFisico.objects.create(
                local_fisico=local,
                base=self.base_c,
            )
        self.assertIn('base', contexto.exception.message_dict)

    def test_uma_base_nao_pode_apontar_para_dois_locais(self):
        primeiro = self._local(nome='Primeiro Local')
        segundo = self._local(nome='Segundo Local')
        VinculoBaseLocalFisico.objects.create(
            local_fisico=primeiro,
            base=self.base_a1,
        )

        with self.assertRaises(ValidationError):
            VinculoBaseLocalFisico.objects.create(
                local_fisico=segundo,
                base=self.base_a1,
            )

    def test_policy_isola_local_de_empresa_nao_relacionada(self):
        compartilhado = self._local()
        VinculoBaseLocalFisico.objects.create(
            local_fisico=compartilhado,
            base=self.base_b,
        )
        isolado = self._local(
            empresa=self.empresa_c,
            nome='Local Isolado',
        )

        self.assertEqual(
            list(LocalFisicoAccessPolicy.locais(
                self.admin_a,
                action=LocalFisicoAccessPolicy.MANAGE,
            )),
            [compartilhado],
        )
        self.assertEqual(
            list(LocalFisicoAccessPolicy.locais(
                self.admin_c,
                action=LocalFisicoAccessPolicy.MANAGE,
            )),
            [isolado],
        )
        self.assertEqual(
            set(LocalFisicoAccessPolicy.locais(self.superuser)),
            {compartilhado, isolado},
        )
        self.assertFalse(
            LocalFisicoAccessPolicy.locais(AnonymousUser()).exists()
        )

    def test_endereco_postal_legado_permanece_independente(self):
        endereco = EnderecoPostalBase.objects.create(
            base=self.base_a1,
            nome_destinatario='Base A1',
            logradouro='Rua Legada',
            numero='10',
            bairro='Centro',
            cidade='São Paulo',
            uf='SP',
            cep='01000-001',
        )
        local = self._local()
        VinculoBaseLocalFisico.objects.create(local_fisico=local, base=self.base_a1)

        self.assertEqual(self.base_a1.endereco_postal, endereco)
        self.assertEqual(self.base_a1.vinculo_local_fisico.local_fisico, local)

    def test_acao_desconhecida_falha_fechada(self):
        self._local()
        self.assertFalse(
            LocalFisicoAccessPolicy.locais(
                self.admin_a,
                action='desconhecida',
            ).exists()
        )
