from django.contrib.auth.models import User
from django.test import TestCase

from estoque.models import (
    Base,
    CapacidadeRelacionamentoEmpresa,
    Empresa,
    Equipamento,
    Perfil,
    Produto,
    RelacionamentoEmpresa,
)
from estoque.security import secure_queryset


class MultiTenantContractTests(TestCase):
    """Contrato ativo de isolamento de Equipamentos entre tenants."""

    @classmethod
    def setUpTestData(cls):
        cls.empresas = {
            chave: Empresa.objects.create(nome=nome)
            for chave, nome in (
                ('empresa_a', 'Empresa A'),
                ('empresa_b', 'Empresa B'),
                ('inventory_brasil', 'Inventory Brasil'),
                ('inventory_latam', 'Inventory LATAM'),
                ('oxxo', 'OXXO'),
            )
        }
        cls.bases = {
            chave: Base.objects.create(
                empresa=empresa,
                nome=f'Base {empresa.nome}',
            )
            for chave, empresa in cls.empresas.items()
        }
        produto = Produto.objects.create(
            codigo='PROD-CONTRATO-MT',
            descricao='Produto do contrato multi-tenant',
            fabricante='Inventory',
            modelo='Contrato',
            categoria='Sistema',
        )
        for indice, (chave, base) in enumerate(cls.bases.items(), start=1):
            Equipamento.objects.create(
                produto=produto,
                numero_serie=f'SERIE-MT-{indice}',
                patrimonio=f'PATRIMONIO-MT-{indice}',
                regional=base,
                status='ATIVO',
                codigo=f'EQP-MT-{indice}',
            )

        cls.superuser = cls._criar_usuario(
            'superuser.mt',
            superuser=True,
        )
        cls.admin_empresa_a = cls._criar_usuario(
            'admin.empresa.a',
            role=Perfil.Role.ADMIN,
            empresa=cls.empresas['empresa_a'],
        )
        cls.admin_empresa_b = cls._criar_usuario(
            'admin.empresa.b',
            role=Perfil.Role.ADMIN,
            empresa=cls.empresas['empresa_b'],
        )
        cls.admin_inventory_brasil = cls._criar_usuario(
            'admin.inventory.brasil',
            role=Perfil.Role.ADMIN,
            empresa=cls.empresas['inventory_brasil'],
        )
        cls.admin_inventory_latam = cls._criar_usuario(
            'admin.inventory.latam',
            role=Perfil.Role.ADMIN,
            empresa=cls.empresas['inventory_latam'],
        )
        cls.admin_oxxo = cls._criar_usuario(
            'admin.oxxo',
            role=Perfil.Role.ADMIN,
            empresa=cls.empresas['oxxo'],
        )
        cls.gestor = cls._criar_usuario(
            'gestor.empresa.a',
            role=Perfil.Role.GESTOR,
            empresa=cls.empresas['empresa_a'],
            bases=(cls.bases['empresa_a'],),
        )
        cls.operador = cls._criar_usuario(
            'operador.empresa.a',
            role=Perfil.Role.OPERADOR,
            empresa=cls.empresas['empresa_a'],
            bases=(cls.bases['empresa_a'],),
        )

        for destination in (
            cls.empresas['inventory_latam'],
            cls.empresas['oxxo'],
        ):
            relationship = RelacionamentoEmpresa.objects.create(
                empresa_origem=cls.empresas['inventory_brasil'],
                empresa_destino=destination,
            )
            CapacidadeRelacionamentoEmpresa.objects.create(
                relacionamento=relationship,
                recurso=CapacidadeRelacionamentoEmpresa.Recurso.EQUIPAMENTOS,
                acao=CapacidadeRelacionamentoEmpresa.Acao.VISUALIZAR,
            )
            cls.admin_inventory_brasil.perfil.empresas_acesso_adicional.add(
                destination
            )

    @classmethod
    def _criar_usuario(
        cls,
        username,
        *,
        role=Perfil.Role.OPERADOR,
        empresa=None,
        bases=(),
        superuser=False,
    ):
        if superuser:
            return User.objects.create_superuser(
                username=username,
                email=f'{username}@example.test',
                password='SenhaDeTeste123!',
            )

        user = User.objects.create_user(
            username=username,
            email=f'{username}@example.test',
            password='SenhaDeTeste123!',
        )
        perfil = user.perfil
        if role == Perfil.Role.ADMIN:
            perfil.role = role
            perfil.empresa = empresa
            perfil.save()
        else:
            perfil.role = role
            perfil.empresa = empresa
            perfil.save()
            perfil.regionais.set(bases)
        return user

    def _empresas_visiveis(self, user):
        return set(
            secure_queryset(Equipamento.objects.all(), user)
            .values_list('regional__empresa_id', flat=True)
        )

    def test_superuser_pode_atravessar_tenants(self):
        self.assertEqual(
            self._empresas_visiveis(self.superuser),
            {empresa.pk for empresa in self.empresas.values()},
        )

    def test_admin_empresa_a_nao_acessa_empresa_b(self):
        self.assertEqual(
            self._empresas_visiveis(self.admin_empresa_a),
            {self.empresas['empresa_a'].pk},
        )

    def test_admin_empresa_b_nao_acessa_empresa_a(self):
        self.assertEqual(
            self._empresas_visiveis(self.admin_empresa_b),
            {self.empresas['empresa_b'].pk},
        )

    def test_admin_inventory_brasil_visualiza_latam_sem_ampliar_para_empresa_a(self):
        empresas_visiveis = self._empresas_visiveis(self.admin_inventory_brasil)
        self.assertIn(self.empresas['inventory_brasil'].pk, empresas_visiveis)
        self.assertIn(self.empresas['inventory_latam'].pk, empresas_visiveis)
        self.assertTrue(empresas_visiveis.isdisjoint({
            self.empresas['empresa_a'].pk,
            self.empresas['empresa_b'].pk,
        }))

    def test_admin_inventory_brasil_visualiza_oxxo_sem_ampliar_para_empresa_b(self):
        empresas_visiveis = self._empresas_visiveis(self.admin_inventory_brasil)
        self.assertIn(self.empresas['inventory_brasil'].pk, empresas_visiveis)
        self.assertIn(self.empresas['oxxo'].pk, empresas_visiveis)
        self.assertTrue(empresas_visiveis.isdisjoint({
            self.empresas['empresa_a'].pk,
            self.empresas['empresa_b'].pk,
        }))

    def test_admin_latam_nao_recebe_acesso_automatico_a_inventory_brasil(self):
        self.assertEqual(
            self._empresas_visiveis(self.admin_inventory_latam),
            {self.empresas['inventory_latam'].pk},
        )

    def test_admin_oxxo_nao_recebe_acesso_automatico_a_inventory_brasil(self):
        self.assertEqual(
            self._empresas_visiveis(self.admin_oxxo),
            {self.empresas['oxxo'].pk},
        )

    def test_gestor_nao_atravessa_tenants(self):
        self.assertEqual(
            self._empresas_visiveis(self.gestor),
            {self.empresas['empresa_a'].pk},
        )

    def test_operador_nao_atravessa_tenants(self):
        self.assertEqual(
            self._empresas_visiveis(self.operador),
            {self.empresas['empresa_a'].pk},
        )
