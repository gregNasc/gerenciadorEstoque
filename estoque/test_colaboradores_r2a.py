from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import ValidationError
from django.test import TestCase

from estoque.models import Base, Colaborador, Empresa, Perfil
from estoque.policies.colaboradores import ColaboradorAccessPolicy


class ColaboradorR2ATests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa_a = Empresa.objects.create(nome='Empresa Colaborador A')
        cls.empresa_b = Empresa.objects.create(nome='Empresa Colaborador B')
        cls.base_a = Base.objects.create(nome='Base A', empresa=cls.empresa_a)
        cls.base_b = Base.objects.create(nome='Base B', empresa=cls.empresa_b)

        cls.admin_a = User.objects.create_user('admin.colaborador.a')
        Perfil.objects.update_or_create(
            user=cls.admin_a,
            defaults={'empresa': cls.empresa_a, 'role': Perfil.Role.ADMIN},
        )
        cls.usuario_a = User.objects.create_user('usuario.colaborador.a')
        Perfil.objects.update_or_create(
            user=cls.usuario_a,
            defaults={'empresa': cls.empresa_a, 'role': Perfil.Role.OPERADOR},
        )
        cls.usuario_b = User.objects.create_user('usuario.colaborador.b')
        Perfil.objects.update_or_create(
            user=cls.usuario_b,
            defaults={'empresa': cls.empresa_b, 'role': Perfil.Role.OPERADOR},
        )
        cls.superuser = User.objects.create_superuser(
            'superuser.colaborador',
            email='superuser@example.com',
            password='test-only-password',
        )

    def test_colaborador_pode_existir_sem_usuario(self):
        colaborador = Colaborador.objects.create(
            empresa=self.empresa_a,
            base=self.base_a,
            nome='  Maria da Silva  ',
            email='  MARIA@EXAMPLE.COM ',
            matricula='  MAT-001 ',
        )

        self.assertIsNone(colaborador.usuario_id)
        self.assertEqual(colaborador.nome, 'MARIA DA SILVA')
        self.assertEqual(colaborador.email, 'maria@example.com')
        self.assertEqual(colaborador.matricula, 'MAT-001')

    def test_usuario_pode_ser_associado_ao_colaborador(self):
        colaborador = Colaborador.objects.create(
            empresa=self.empresa_a,
            base=self.base_a,
            usuario=self.usuario_a,
            nome='Usuário Associado',
        )

        self.assertEqual(colaborador.usuario, self.usuario_a)
        self.assertEqual(self.usuario_a.colaborador_custodia, colaborador)

    def test_base_de_outro_tenant_e_rejeitada(self):
        with self.assertRaises(ValidationError) as contexto:
            Colaborador.objects.create(
                empresa=self.empresa_a,
                base=self.base_b,
                nome='Base Inválida',
            )

        self.assertIn('base', contexto.exception.message_dict)

    def test_usuario_de_outro_tenant_e_rejeitado(self):
        with self.assertRaises(ValidationError) as contexto:
            Colaborador.objects.create(
                empresa=self.empresa_a,
                base=self.base_a,
                usuario=self.usuario_b,
                nome='Usuário Inválido',
            )

        self.assertIn('usuario', contexto.exception.message_dict)

    def test_matricula_e_unica_por_empresa_quando_informada(self):
        Colaborador.objects.create(
            empresa=self.empresa_a,
            nome='Primeiro',
            matricula='MAT-UNICA',
        )
        with self.assertRaises(ValidationError):
            Colaborador.objects.create(
                empresa=self.empresa_a,
                nome='Segundo',
                matricula='MAT-UNICA',
            )
        Colaborador.objects.create(
            empresa=self.empresa_b,
            nome='Mesmo identificador em outro tenant',
            matricula='MAT-UNICA',
        )

    def test_policy_isola_colaboradores_por_tenant(self):
        colaborador_a = Colaborador.objects.create(
            empresa=self.empresa_a,
            base=self.base_a,
            nome='Colaborador A',
        )
        colaborador_b = Colaborador.objects.create(
            empresa=self.empresa_b,
            base=self.base_b,
            nome='Colaborador B',
        )

        self.assertEqual(
            list(ColaboradorAccessPolicy.colaboradores(
                self.admin_a,
                action=ColaboradorAccessPolicy.MANAGE,
            )),
            [colaborador_a],
        )
        self.assertEqual(
            set(ColaboradorAccessPolicy.colaboradores(self.superuser)),
            {colaborador_a, colaborador_b},
        )
        self.assertFalse(
            ColaboradorAccessPolicy.colaboradores(AnonymousUser()).exists()
        )

    def test_acao_desconhecida_falha_fechada(self):
        Colaborador.objects.create(
            empresa=self.empresa_a,
            nome='Colaborador fechado',
        )
        self.assertFalse(
            ColaboradorAccessPolicy.colaboradores(
                self.admin_a,
                action='desconhecida',
            ).exists()
        )
