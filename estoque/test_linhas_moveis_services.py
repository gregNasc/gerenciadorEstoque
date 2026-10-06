from cryptography.fernet import Fernet
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.test import TestCase, override_settings

from compras.models import (
    CapacidadeCatalogoProdutoEmpresa,
    CatalogoProdutoEmpresa,
)
from estoque.models import (
    Base,
    CredencialLinhaMovel,
    Empresa,
    Equipamento,
    HistoricoLinhaMovel,
    LinhaMovel,
    OperadoraMovel,
    Perfil,
    Produto,
    Transferencia,
    TransferenciaItem,
    VinculoLinhaEquipamento,
)
from estoque.policies.linhas_moveis import LinhasMoveisAccessPolicy
from estoque.services.linhas_moveis_service import (
    CredenciaisLinhaMovelService,
    LinhasMoveisService,
)
from estoque.services.transferencia_services import receber_transferencia


class LinhasMoveisServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa_a = Empresa.objects.create(nome='Empresa Service A')
        cls.empresa_b = Empresa.objects.create(nome='Empresa Service B')
        cls.base_a = Base.objects.create(nome='Base Service A', empresa=cls.empresa_a)
        cls.base_a_2 = Base.objects.create(nome='Base Service A2', empresa=cls.empresa_a)
        cls.base_b = Base.objects.create(nome='Base Service B', empresa=cls.empresa_b)

        cls.admin_a = User.objects.create_user('admin_service_a')
        Perfil.objects.update_or_create(
            user=cls.admin_a,
            defaults={'empresa': cls.empresa_a, 'role': Perfil.Role.ADMIN},
        )
        cls.admin_b = User.objects.create_user('admin_service_b')
        Perfil.objects.update_or_create(
            user=cls.admin_b,
            defaults={'empresa': cls.empresa_b, 'role': Perfil.Role.ADMIN},
        )
        cls.gestor_a = User.objects.create_user('gestor_service_a')
        perfil_gestor, _ = Perfil.objects.update_or_create(
            user=cls.gestor_a,
            defaults={'empresa': cls.empresa_a, 'role': Perfil.Role.GESTOR},
        )
        perfil_gestor.regionais.add(cls.base_a)
        cls.operador_a = User.objects.create_user('operador_service_a')
        perfil_operador, _ = Perfil.objects.update_or_create(
            user=cls.operador_a,
            defaults={'empresa': cls.empresa_a, 'role': Perfil.Role.OPERADOR},
        )
        perfil_operador.regionais.add(cls.base_a)

        cls.operadora_a = OperadoraMovel.objects.create(
            empresa=cls.empresa_a,
            nome='Operadora Service A',
        )
        cls.operadora_b = OperadoraMovel.objects.create(
            empresa=cls.empresa_b,
            nome='Operadora Service B',
        )
        cls.produto = Produto.objects.create(
            codigo='MOV-SERVICE',
            descricao='Produto móvel service',
            fabricante='Fabricante',
            modelo='Modelo',
            categoria='Configurável',
        )
        catalogo_a = CatalogoProdutoEmpresa.objects.create(
            empresa=cls.empresa_a,
            produto=cls.produto,
        )
        CatalogoProdutoEmpresa.objects.create(
            empresa=cls.empresa_b,
            produto=cls.produto,
        )
        CapacidadeCatalogoProdutoEmpresa.objects.create(
            catalogo=catalogo_a,
            codigo=CapacidadeCatalogoProdutoEmpresa.CONECTIVIDADE_MOVEL,
        )
        cls.equipamento_a = Equipamento.objects.create(
            produto=cls.produto,
            numero_serie='SER-MOV-SERVICE-A',
            patrimonio='PAT-MOV-SERVICE-A',
            regional=cls.base_a,
            codigo='EQ-MOV-SERVICE-A',
        )
        cls.equipamento_a_2 = Equipamento.objects.create(
            produto=cls.produto,
            numero_serie='SER-MOV-SERVICE-A2',
            patrimonio='PAT-MOV-SERVICE-A2',
            regional=cls.base_a,
            codigo='EQ-MOV-SERVICE-A2',
        )
        cls.linha_a = LinhaMovel.objects.create(
            empresa=cls.empresa_a,
            base=cls.base_a,
            numero_normalizado='+5511988881001',
            operadora=cls.operadora_a,
            iccid='8955012345678810001',
            criado_por=cls.admin_a,
        )
        cls.linha_a_2 = LinhaMovel.objects.create(
            empresa=cls.empresa_a,
            base=cls.base_a,
            numero_normalizado='+5511988881002',
            operadora=cls.operadora_a,
            iccid='8955012345678810002',
            criado_por=cls.admin_a,
        )
        cls.linha_a_outra_base = LinhaMovel.objects.create(
            empresa=cls.empresa_a,
            base=cls.base_a_2,
            numero_normalizado='+5511988881003',
            operadora=cls.operadora_a,
            iccid='8955012345678810003',
            criado_por=cls.admin_a,
        )
        cls.linha_b = LinhaMovel.objects.create(
            empresa=cls.empresa_b,
            base=cls.base_b,
            numero_normalizado='+5511988882001',
            operadora=cls.operadora_b,
            iccid='8955012345678820001',
            criado_por=cls.admin_b,
        )

        cls.permissao_view = Permission.objects.get(codename='visualizar_linhas_moveis')
        cls.permissao_link = Permission.objects.get(codename='vincular_linhas_moveis')
        cls.permissao_secret = Permission.objects.get(
            codename='visualizar_credenciais_linhas_moveis'
        )
        cls.gestor_a.user_permissions.add(cls.permissao_view, cls.permissao_link)
        cls.operador_a.user_permissions.add(cls.permissao_view, cls.permissao_link)

    def setUp(self):
        # Reproduz identidades carregadas em uma requisição e descarta o Perfil
        # inicial que o signal de User pode ter deixado no cache do objeto.
        self.admin_a = User.objects.get(pk=self.admin_a.pk)
        self.admin_b = User.objects.get(pk=self.admin_b.pk)
        self.gestor_a = User.objects.get(pk=self.gestor_a.pk)
        self.operador_a = User.objects.get(pk=self.operador_a.pk)

    @staticmethod
    def _clear_permission_cache(user):
        for atributo in ('_perm_cache', '_user_perm_cache', '_group_perm_cache'):
            user.__dict__.pop(atributo, None)

    @classmethod
    def _key_config(cls, key_id='v1', key=None):
        key = key or Fernet.generate_key().decode('ascii')
        return [f'{key_id}:{key}']

    def test_somente_admin_visualiza_linhas_moveis(self):
        self.assertEqual(
            set(LinhasMoveisAccessPolicy.linhas(self.admin_a).values_list('pk', flat=True)),
            {self.linha_a.pk, self.linha_a_2.pk, self.linha_a_outra_base.pk},
        )
        self.assertEqual(
            set(LinhasMoveisAccessPolicy.linhas(self.gestor_a).values_list('pk', flat=True)),
            set(),
        )
        with self.assertRaises(PermissionDenied):
            LinhasMoveisAccessPolicy.obter_linha(
                self.admin_a,
                self.linha_b.pk,
                action=LinhasMoveisAccessPolicy.MANAGE,
            )

    def test_operador_nao_visualiza_nem_vincula_linha(self):
        LinhasMoveisService.vincular(
            usuario=self.admin_a,
            linha_id=self.linha_a.pk,
            equipamento_id=self.equipamento_a.pk,
        )

        self.assertEqual(
            list(LinhasMoveisAccessPolicy.linhas(self.operador_a).values_list('pk', flat=True)),
            [],
        )
        self.assertFalse(
            LinhasMoveisAccessPolicy.permite(
                self.operador_a,
                LinhasMoveisAccessPolicy.LINK,
            )
        )

    def test_gestor_com_permissao_nao_pode_vincular(self):
        with self.assertRaises(PermissionDenied):
            LinhasMoveisService.vincular(
                usuario=self.gestor_a,
                linha_id=self.linha_a.pk,
                equipamento_id=self.equipamento_a.pk,
            )

    def test_vincular_e_desvincular_atualiza_status_e_historico(self):
        vinculo = LinhasMoveisService.vincular(
            usuario=self.admin_a,
            linha_id=self.linha_a.pk,
            equipamento_id=self.equipamento_a.pk,
        )
        self.linha_a.refresh_from_db()
        self.assertEqual(self.linha_a.status, LinhaMovel.Status.EM_USO)
        self.assertTrue(
            HistoricoLinhaMovel.objects.filter(
                linha=self.linha_a,
                evento=HistoricoLinhaMovel.Evento.VINCULO,
            ).exists()
        )

        encerrado = LinhasMoveisService.desvincular(
            usuario=self.admin_a,
            linha_id=self.linha_a.pk,
            motivo='Troca controlada',
        )
        self.linha_a.refresh_from_db()
        self.assertEqual(encerrado.pk, vinculo.pk)
        self.assertIsNotNone(encerrado.fim_em)
        self.assertEqual(self.linha_a.status, LinhaMovel.Status.DISPONIVEL)
        self.assertEqual(self.linha_a.vinculos_equipamento.count(), 1)

    def test_troca_preserva_vinculo_anterior_e_registra_evento(self):
        anterior = LinhasMoveisService.vincular(
            usuario=self.admin_a,
            linha_id=self.linha_a.pk,
            equipamento_id=self.equipamento_a.pk,
        )

        encerrado, novo = LinhasMoveisService.trocar(
            usuario=self.admin_a,
            equipamento_id=self.equipamento_a.pk,
            nova_linha_id=self.linha_a_2.pk,
            motivo='Substituição operacional',
        )

        anterior.refresh_from_db()
        self.linha_a.refresh_from_db()
        self.linha_a_2.refresh_from_db()
        self.assertEqual(encerrado.pk, anterior.pk)
        self.assertIsNotNone(anterior.fim_em)
        self.assertEqual(self.linha_a.status, LinhaMovel.Status.DISPONIVEL)
        self.assertEqual(self.linha_a_2.status, LinhaMovel.Status.EM_USO)
        self.assertEqual(novo.equipamento, self.equipamento_a)
        self.assertTrue(self.linha_a.historico.filter(
            evento=HistoricoLinhaMovel.Evento.TROCA,
        ).exists())
        self.assertTrue(self.linha_a_2.historico.filter(
            evento=HistoricoLinhaMovel.Evento.TROCA,
        ).exists())

    def test_transferencia_na_mesma_empresa_move_base_da_linha(self):
        LinhasMoveisService.vincular(
            usuario=self.admin_a,
            linha_id=self.linha_a.pk,
            equipamento_id=self.equipamento_a.pk,
        )

        LinhasMoveisService.preparar_transferencia_base(
            usuario=self.admin_a,
            equipamento=self.equipamento_a,
            nova_base=self.base_a_2,
        )

        self.linha_a.refresh_from_db()
        self.assertEqual(self.linha_a.base, self.base_a_2)
        historico = self.linha_a.historico.get(
            evento=HistoricoLinhaMovel.Evento.ALTERACAO,
        )
        self.assertEqual(historico.metadados['base_anterior_id'], self.base_a.pk)
        self.assertEqual(historico.metadados['nova_base_id'], self.base_a_2.pk)

    def test_transferencia_entre_empresas_exige_desvinculo(self):
        LinhasMoveisService.vincular(
            usuario=self.admin_a,
            linha_id=self.linha_a.pk,
            equipamento_id=self.equipamento_a.pk,
        )

        with self.assertRaisesMessage(ValidationError, 'Desvincule a linha móvel'):
            LinhasMoveisService.preparar_transferencia_base(
                usuario=self.admin_a,
                equipamento=self.equipamento_a,
                nova_base=self.base_b,
            )

        self.linha_a.refresh_from_db()
        self.assertEqual(self.linha_a.base, self.base_a)

    def test_recebimento_de_transferencia_move_equipamento_e_linha_juntos(self):
        LinhasMoveisService.vincular(
            usuario=self.admin_a,
            linha_id=self.linha_a.pk,
            equipamento_id=self.equipamento_a.pk,
        )
        transferencia = Transferencia.objects.create(
            solicitado_por=self.admin_a,
            regional_origem=self.base_a,
            regional_destino=self.base_a_2,
            status=Transferencia.Status.EM_TRANSITO,
            protocolo='TR-R1E-SERVICE',
        )
        TransferenciaItem.objects.create(
            transferencia=transferencia,
            equipamento=self.equipamento_a,
        )

        receber_transferencia(transferencia, self.admin_a)

        self.equipamento_a.refresh_from_db()
        self.linha_a.refresh_from_db()
        self.assertEqual(self.equipamento_a.regional, self.base_a_2)
        self.assertEqual(self.linha_a.base, self.base_a_2)

    def test_recebimento_legado_falha_fechado_sem_usuario_responsavel(self):
        LinhasMoveisService.vincular(
            usuario=self.admin_a,
            linha_id=self.linha_a.pk,
            equipamento_id=self.equipamento_a.pk,
        )
        transferencia = Transferencia.objects.create(
            solicitado_por=self.admin_a,
            regional_origem=self.base_a,
            regional_destino=self.base_a_2,
            status=Transferencia.Status.EM_TRANSITO,
            protocolo='TR-R1E-LEGADO',
        )
        TransferenciaItem.objects.create(
            transferencia=transferencia,
            equipamento=self.equipamento_a,
        )

        with self.assertRaisesMessage(ValidationError, 'usuário responsável'):
            transferencia.receber()

        transferencia.refresh_from_db()
        self.equipamento_a.refresh_from_db()
        self.linha_a.refresh_from_db()
        self.assertEqual(transferencia.status, Transferencia.Status.EM_TRANSITO)
        self.assertEqual(self.equipamento_a.regional, self.base_a)
        self.assertEqual(self.linha_a.base, self.base_a)

    def test_falha_de_vinculo_nao_altera_estado_da_linha(self):
        LinhasMoveisService.vincular(
            usuario=self.admin_a,
            linha_id=self.linha_a.pk,
            equipamento_id=self.equipamento_a.pk,
        )

        with self.assertRaises(ValidationError):
            LinhasMoveisService.vincular(
                usuario=self.admin_a,
                linha_id=self.linha_a_2.pk,
                equipamento_id=self.equipamento_a.pk,
            )
        self.linha_a_2.refresh_from_db()
        self.assertEqual(self.linha_a_2.status, LinhaMovel.Status.DISPONIVEL)
        self.assertFalse(self.linha_a_2.historico.exists())

    def test_inativacao_encerra_vinculo_e_reativacao_nao_o_restaura(self):
        vinculo = LinhasMoveisService.vincular(
            usuario=self.admin_a,
            linha_id=self.linha_a.pk,
            equipamento_id=self.equipamento_a.pk,
        )
        LinhasMoveisService.inativar(
            usuario=self.admin_a,
            linha_id=self.linha_a.pk,
            motivo='Contrato encerrado',
        )
        self.linha_a.refresh_from_db()
        vinculo.refresh_from_db()
        self.assertEqual(self.linha_a.status, LinhaMovel.Status.INATIVA)
        self.assertIsNotNone(vinculo.fim_em)

        LinhasMoveisService.reativar(usuario=self.admin_a, linha_id=self.linha_a.pk)
        self.linha_a.refresh_from_db()
        self.assertEqual(self.linha_a.status, LinhaMovel.Status.DISPONIVEL)
        self.assertFalse(
            self.linha_a.vinculos_equipamento.filter(fim_em__isnull=True).exists()
        )

    def test_admin_nao_recebe_credenciais_por_papel_implicito(self):
        self.assertFalse(
            LinhasMoveisAccessPolicy.permite(
                self.admin_a,
                LinhasMoveisAccessPolicy.VIEW_SECRETS,
            )
        )
        with self.assertRaises(PermissionDenied):
            CredenciaisLinhaMovelService.ler(
                usuario=self.admin_a,
                linha_id=self.linha_a.pk,
            )

    def test_credenciais_sao_cifradas_mascaradas_e_lidas_com_permissao(self):
        self.admin_a.user_permissions.add(self.permissao_secret)
        self._clear_permission_cache(self.admin_a)
        config = self._key_config()
        with override_settings(LINHAS_MOVEIS_CREDENTIAL_KEYS=config):
            credencial = CredenciaisLinhaMovelService.salvar(
                usuario=self.admin_a,
                linha_id=self.linha_a.pk,
                pin='1234',
                puk='87654321',
            )
            self.assertEqual(credencial.chave_id, 'v1')
            self.assertTrue(credencial.conteudo_criptografado.startswith('gAAAA'))
            self.assertNotIn('1234', credencial.conteudo_criptografado)
            self.assertNotIn('87654321', credencial.conteudo_criptografado)
            self.assertEqual(
                CredenciaisLinhaMovelService.ler(
                    usuario=self.admin_a,
                    linha_id=self.linha_a.pk,
                ),
                {'pin': '1234', 'puk': '87654321'},
            )

        self.admin_a.user_permissions.remove(self.permissao_secret)
        self._clear_permission_cache(self.admin_a)
        with override_settings(LINHAS_MOVEIS_CREDENTIAL_KEYS=[]):
            self.assertEqual(
                CredenciaisLinhaMovelService.mascaradas(
                    usuario=self.admin_a,
                    linha_id=self.linha_a.pk,
                ),
                {'pin': '••••', 'puk': '••••'},
            )

    def test_permissao_de_credencial_nao_amplia_escopo_de_tenant(self):
        self.admin_a.user_permissions.add(self.permissao_secret)
        self._clear_permission_cache(self.admin_a)

        with override_settings(LINHAS_MOVEIS_CREDENTIAL_KEYS=self._key_config()):
            with self.assertRaises(PermissionDenied):
                CredenciaisLinhaMovelService.ler(
                    usuario=self.admin_a,
                    linha_id=self.linha_b.pk,
                )

    def test_ausencia_de_chave_falha_fechada_sem_impedir_linha_comum(self):
        self.admin_a.user_permissions.add(self.permissao_secret)
        self._clear_permission_cache(self.admin_a)

        with override_settings(LINHAS_MOVEIS_CREDENTIAL_KEYS=[]):
            with self.assertRaises(ImproperlyConfigured):
                CredenciaisLinhaMovelService.salvar(
                    usuario=self.admin_a,
                    linha_id=self.linha_a.pk,
                    pin='1234',
                )
        self.assertTrue(LinhaMovel.objects.filter(pk=self.linha_a.pk).exists())
        self.assertFalse(CredencialLinhaMovel.objects.filter(linha=self.linha_a).exists())

    def test_rotacao_le_chave_anterior_sem_usar_secret_key(self):
        self.admin_a.user_permissions.add(self.permissao_secret)
        self._clear_permission_cache(self.admin_a)
        old_key = Fernet.generate_key().decode('ascii')
        new_key = Fernet.generate_key().decode('ascii')

        with override_settings(
            LINHAS_MOVEIS_CREDENTIAL_KEYS=self._key_config('anterior', old_key),
        ):
            CredenciaisLinhaMovelService.salvar(
                usuario=self.admin_a,
                linha_id=self.linha_a.pk,
                pin2='5678',
            )
        with override_settings(
            LINHAS_MOVEIS_CREDENTIAL_KEYS=[
                *self._key_config('atual', new_key),
                *self._key_config('anterior', old_key),
            ],
        ):
            self.assertEqual(
                CredenciaisLinhaMovelService.ler(
                    usuario=self.admin_a,
                    linha_id=self.linha_a.pk,
                ),
                {'pin2': '5678'},
            )

    def test_historico_de_credencial_nao_contem_segredos(self):
        self.admin_a.user_permissions.add(self.permissao_secret)
        self._clear_permission_cache(self.admin_a)
        with override_settings(
            LINHAS_MOVEIS_CREDENTIAL_KEYS=self._key_config(),
        ):
            CredenciaisLinhaMovelService.salvar(
                usuario=self.admin_a,
                linha_id=self.linha_a.pk,
                pin='1234',
                puk2='12345678',
            )

        historico = self.linha_a.historico.get(
            evento=HistoricoLinhaMovel.Evento.ALTERACAO,
        )
        texto = str(historico.metadados)
        self.assertNotIn('1234', texto)
        self.assertNotIn('12345678', texto)
        self.assertEqual(historico.metadados['quantidade_credenciais'], 2)
