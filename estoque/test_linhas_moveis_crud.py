from cryptography.fernet import Fernet
from django.contrib.auth.models import Permission, User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from compras.models import (
    CapacidadeCatalogoProdutoEmpresa,
    CatalogoProdutoEmpresa,
)
from estoque.models import (
    Base,
    CredencialLinhaMovel,
    Empresa,
    HistoricoLinhaMovel,
    LinhaMovel,
    Modulo,
    ModuloEmpresa,
    OperadoraMovel,
    Perfil,
    Produto,
)


class LinhasMoveisCrudTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa_a = Empresa.objects.create(nome='Empresa CRUD A')
        cls.empresa_b = Empresa.objects.create(nome='Empresa CRUD B')
        cls.empresa_sem_capacidade = Empresa.objects.create(nome='Empresa CRUD Sem Capacidade')
        cls.base_a = Base.objects.create(nome='Base CRUD A', empresa=cls.empresa_a)
        cls.base_b = Base.objects.create(nome='Base CRUD B', empresa=cls.empresa_b)
        cls.base_sem_capacidade = Base.objects.create(
            nome='Base sem capacidade', empresa=cls.empresa_sem_capacidade,
        )

        cls.admin_a = User.objects.create_user('admin_crud_a')
        Perfil.objects.update_or_create(
            user=cls.admin_a,
            defaults={'empresa': cls.empresa_a, 'role': Perfil.Role.ADMIN},
        )
        cls.admin_b = User.objects.create_user('admin_crud_b')
        Perfil.objects.update_or_create(
            user=cls.admin_b,
            defaults={'empresa': cls.empresa_b, 'role': Perfil.Role.ADMIN},
        )
        cls.admin_sem_capacidade = User.objects.create_user('admin_crud_sem_cap')
        Perfil.objects.update_or_create(
            user=cls.admin_sem_capacidade,
            defaults={
                'empresa': cls.empresa_sem_capacidade,
                'role': Perfil.Role.ADMIN,
            },
        )
        cls.responsavel_a = User.objects.create_user(
            'responsavel_linha_a', first_name='Responsável', last_name='Móvel',
        )
        perfil_responsavel, _ = Perfil.objects.update_or_create(
            user=cls.responsavel_a,
            defaults={'empresa': cls.empresa_a, 'role': Perfil.Role.OPERADOR},
        )
        perfil_responsavel.regionais.add(cls.base_a)
        cls.gestor_a = User.objects.create_user('gestor_crud_linhas')
        perfil_gestor, _ = Perfil.objects.update_or_create(
            user=cls.gestor_a,
            defaults={'empresa': cls.empresa_a, 'role': Perfil.Role.GESTOR},
        )
        perfil_gestor.regionais.add(cls.base_a)
        cls.operador_a = User.objects.create_user('operador_crud_linhas')
        perfil_operador, _ = Perfil.objects.update_or_create(
            user=cls.operador_a,
            defaults={'empresa': cls.empresa_a, 'role': Perfil.Role.OPERADOR},
        )
        perfil_operador.regionais.add(cls.base_a)

        for codigo, nome in (
            (Modulo.Codigo.EQUIPAMENTOS, 'Equipamentos'),
            (Modulo.Codigo.CADASTROS, 'Cadastros'),
        ):
            modulo, _ = Modulo.objects.update_or_create(
                codigo=codigo,
                defaults={'nome': nome, 'ativo': True},
            )
            for empresa in (cls.empresa_a, cls.empresa_b, cls.empresa_sem_capacidade):
                ModuloEmpresa.objects.update_or_create(
                    empresa=empresa,
                    modulo=modulo,
                    defaults={'habilitado': True},
                )

        cls.produto = Produto.objects.create(
            codigo='MOV-CRUD',
            descricao='Produto móvel CRUD',
            fabricante='Fabricante',
            modelo='Modelo',
            categoria='Móvel configurável',
        )
        for empresa in (cls.empresa_a, cls.empresa_b):
            catalogo = CatalogoProdutoEmpresa.objects.create(
                empresa=empresa,
                produto=cls.produto,
            )
            CapacidadeCatalogoProdutoEmpresa.objects.create(
                catalogo=catalogo,
                codigo=CapacidadeCatalogoProdutoEmpresa.CONECTIVIDADE_MOVEL,
            )
        cls.operadora_a = OperadoraMovel.objects.create(
            empresa=cls.empresa_a,
            nome='Operadora CRUD A',
        )
        cls.operadora_b = OperadoraMovel.objects.create(
            empresa=cls.empresa_b,
            nome='Operadora CRUD B',
        )
        cls.linha_a = LinhaMovel.objects.create(
            empresa=cls.empresa_a,
            base=cls.base_a,
            numero_normalizado='+5511977771001',
            operadora=cls.operadora_a,
            iccid='8955012345678710001',
            criado_por=cls.admin_a,
        )
        cls.linha_b = LinhaMovel.objects.create(
            empresa=cls.empresa_b,
            base=cls.base_b,
            numero_normalizado='+5511977772001',
            operadora=cls.operadora_b,
            iccid='8955012345678720001',
            criado_por=cls.admin_b,
        )
        cls.secret_permission = Permission.objects.get(
            codename='visualizar_credenciais_linhas_moveis'
        )
        cls.manage_permission = Permission.objects.get(
            codename='gerenciar_linhas_moveis'
        )
        cls.gestor_a.user_permissions.add(cls.manage_permission)
        cls.operador_a.user_permissions.add(cls.manage_permission)

    def setUp(self):
        self.client = Client()

    def login(self, user):
        self.client.force_login(User.objects.get(pk=user.pk))

    def test_listagem_isola_tenant_e_mascara_iccid(self):
        self.login(self.admin_a)

        response = self.client.get(reverse('estoque:lista_linhas_moveis'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '(11) 97777-1001')
        self.assertNotContains(response, '(11) 97777-2001')
        self.assertContains(response, '••••0001')
        self.assertNotContains(response, self.linha_a.iccid)

    def test_superuser_mantem_acesso_mesmo_com_perfil_nao_admin(self):
        superusuario = User.objects.create_superuser(
            'superuser_linhas_moveis',
            email='superuser-linhas@example.com',
            password='senha-superuser-segura',
        )
        Perfil.objects.update_or_create(
            user=superusuario,
            defaults={'empresa': self.empresa_a, 'role': Perfil.Role.GESTOR},
        )
        self.login(superusuario)

        lista = self.client.get(reverse('estoque:lista_linhas_moveis'))
        cadastro = self.client.get(reverse('estoque:criar_linha_movel'))
        edicao = self.client.get(reverse(
            'estoque:editar_linha_movel', args=[self.linha_a.pk],
        ))

        self.assertEqual(lista.status_code, 200)
        self.assertContains(lista, 'Linhas móveis')
        self.assertEqual(cadastro.status_code, 200)
        self.assertEqual(edicao.status_code, 200)

    def test_empresa_sem_capacidade_nao_lista_nem_cadastra_linhas(self):
        self.login(self.admin_sem_capacidade)

        response = self.client.get(reverse('estoque:lista_linhas_moveis'))
        cadastro = self.client.get(reverse('estoque:criar_linha_movel'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nenhuma linha móvel encontrada neste escopo.')
        self.assertNotContains(response, 'Nova linha')
        self.assertEqual(cadastro.status_code, 403)

    def test_cadastro_normaliza_numero_e_registra_historico(self):
        self.login(self.admin_a)
        response = self.client.post(reverse('estoque:criar_linha_movel'), {
            'empresa': self.empresa_a.pk,
            'base': self.base_a.pk,
            'numero_normalizado': '(11) 96666-1234',
            'operadora': self.operadora_a.pk,
            'iccid': '8955012345678710099',
            'observacao': 'Linha operacional',
        })

        self.assertRedirects(response, reverse('estoque:lista_linhas_moveis'))
        linha = LinhaMovel.objects.get(numero_normalizado='+5511966661234')
        self.assertEqual(linha.empresa, self.empresa_a)
        self.assertTrue(
            linha.historico.filter(evento=HistoricoLinhaMovel.Evento.CADASTRO).exists()
        )

    def test_admin_pode_atribuir_usuario_da_mesma_empresa_e_base(self):
        self.login(self.admin_a)
        response = self.client.post(reverse('estoque:criar_linha_movel'), {
            'empresa': self.empresa_a.pk,
            'base': self.base_a.pk,
            'numero_normalizado': '(11) 96666-5678',
            'operadora': self.operadora_a.pk,
            'usuario_responsavel': self.responsavel_a.pk,
            'iccid': '8955012345678710088',
            'observacao': '',
        })

        self.assertRedirects(response, reverse('estoque:lista_linhas_moveis'))
        linha = LinhaMovel.objects.get(numero_normalizado='+5511966665678')
        self.assertEqual(linha.usuario_responsavel, self.responsavel_a)

        lista = self.client.get(reverse('estoque:lista_linhas_moveis'))
        self.assertContains(lista, self.responsavel_a.username)

    def test_usuario_responsavel_pode_ser_qualquer_usuario_ativo_do_sistema(self):
        self.login(self.admin_a)
        response = self.client.post(reverse('estoque:criar_linha_movel'), {
            'empresa': self.empresa_a.pk,
            'base': self.base_a.pk,
            'numero_normalizado': '(11) 96666-9876',
            'operadora': self.operadora_a.pk,
            'usuario_responsavel': self.admin_b.pk,
            'iccid': '8955012345678710077',
            'observacao': '',
        })

        self.assertRedirects(response, reverse('estoque:lista_linhas_moveis'))
        linha = LinhaMovel.objects.get(numero_normalizado='+5511966669876')
        self.assertEqual(linha.usuario_responsavel, self.admin_b)

    def test_colaborador_sem_acesso_pode_ser_cadastrado_e_editado_por_nome(self):
        self.login(self.admin_a)
        response = self.client.post(reverse('estoque:criar_linha_movel'), {
            'empresa': self.empresa_a.pk,
            'base': self.base_a.pk,
            'numero_normalizado': '(11) 96666-8765',
            'operadora': self.operadora_a.pk,
            'responsavel_nome': 'Colaborador Externo Inicial',
            'iccid': '8955012345678710066',
            'observacao': '',
        })
        self.assertRedirects(response, reverse('estoque:lista_linhas_moveis'))
        linha = LinhaMovel.objects.get(numero_normalizado='+5511966668765')
        self.assertEqual(linha.responsavel_nome, 'COLABORADOR EXTERNO INICIAL')

        response = self.client.post(reverse(
            'estoque:editar_linha_movel', args=[linha.pk],
        ), {
            'empresa': self.empresa_a.pk,
            'base': self.base_a.pk,
            'numero_normalizado': linha.numero_normalizado,
            'operadora': self.operadora_a.pk,
            'responsavel_nome': 'Colaborador Externo Atualizado',
            'iccid': linha.iccid,
            'observacao': '',
        })
        self.assertRedirects(response, reverse('estoque:lista_linhas_moveis'))
        linha.refresh_from_db()
        self.assertEqual(linha.responsavel_nome, 'COLABORADOR EXTERNO ATUALIZADO')

    def test_gestor_e_operador_com_permissao_nao_acessam_linhas_moveis(self):
        for usuario in (self.gestor_a, self.operador_a):
            with self.subTest(usuario=usuario.username):
                self.login(usuario)

                cadastro = self.client.get(reverse('estoque:criar_linha_movel'))
                lista = self.client.get(reverse('estoque:lista_linhas_moveis'))
                edicao = self.client.get(reverse(
                    'estoque:editar_linha_movel', args=[self.linha_a.pk],
                ))

                self.assertEqual(cadastro.status_code, 403)
                self.assertEqual(lista.status_code, 403)
                self.assertEqual(edicao.status_code, 403)

    def test_cadastro_forjado_de_outro_tenant_e_rejeitado(self):
        self.login(self.admin_a)
        response = self.client.post(reverse('estoque:criar_linha_movel'), {
            'empresa': self.empresa_b.pk,
            'base': self.base_b.pk,
            'numero_normalizado': '+5511966664321',
            'operadora': self.operadora_b.pk,
            'iccid': '8955012345678720099',
            'observacao': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            LinhaMovel.objects.filter(numero_normalizado='+5511966664321').exists()
        )

    def test_edicao_de_outro_tenant_retorna_403(self):
        self.login(self.admin_a)

        response = self.client.get(reverse(
            'estoque:editar_linha_movel', args=[self.linha_b.pk],
        ))

        self.assertEqual(response.status_code, 403)

    def test_edicao_atualiza_linha_e_registra_apenas_campos_no_historico(self):
        self.login(self.admin_a)

        response = self.client.post(reverse(
            'estoque:editar_linha_movel', args=[self.linha_a.pk],
        ), {
            'empresa': self.empresa_a.pk,
            'base': self.base_a.pk,
            'numero_normalizado': '(11) 95555-1001',
            'operadora': self.operadora_a.pk,
            'iccid': '8955012345678710011',
            'observacao': 'Linha atualizada',
        })

        self.assertRedirects(response, reverse('estoque:lista_linhas_moveis'))
        self.linha_a.refresh_from_db()
        self.assertEqual(self.linha_a.numero_normalizado, '+5511955551001')
        historico = self.linha_a.historico.get(
            evento=HistoricoLinhaMovel.Evento.ALTERACAO,
        )
        self.assertEqual(
            set(historico.metadados['campos_alterados']),
            {'numero_normalizado', 'iccid', 'observacao'},
        )
        self.assertNotIn('8955012345678710011', str(historico.metadados))

    def test_crud_de_operadora_permanece_no_tenant(self):
        self.login(self.admin_a)
        response = self.client.post(reverse('estoque:operadoras_moveis'), {
            'empresa': self.empresa_a.pk,
            'nome': 'Nova Operadora A',
            'codigo': 'nova-a',
            'ativa': 'on',
        })
        self.assertRedirects(response, reverse('estoque:operadoras_moveis'))
        criada = OperadoraMovel.objects.get(empresa=self.empresa_a, nome='NOVA OPERADORA A')

        lista = self.client.get(reverse('estoque:operadoras_moveis'))
        self.assertContains(lista, criada.nome)
        self.assertNotContains(lista, self.operadora_b.nome)

        editar = self.client.post(reverse(
            'estoque:editar_operadora_movel', args=[criada.pk],
        ), {
            'empresa': self.empresa_a.pk,
            'nome': 'Operadora A Editada',
            'codigo': 'editada-a',
            'ativa': 'on',
        })
        self.assertRedirects(editar, reverse('estoque:operadoras_moveis'))
        criada.refresh_from_db()
        self.assertEqual(criada.nome, 'OPERADORA A EDITADA')

        alternar = self.client.post(reverse(
            'estoque:alternar_operadora_movel', args=[criada.pk],
        ))
        self.assertRedirects(alternar, reverse('estoque:operadoras_moveis'))
        criada.refresh_from_db()
        self.assertFalse(criada.ativa)

    def test_inativar_exige_post_e_reativar_preserva_registro(self):
        self.login(self.admin_a)
        url_inativar = reverse('estoque:inativar_linha_movel', args=[self.linha_a.pk])
        self.assertEqual(self.client.get(url_inativar).status_code, 405)

        response = self.client.post(url_inativar, {'motivo': 'Contrato encerrado'})
        self.assertRedirects(response, reverse('estoque:lista_linhas_moveis'))
        self.linha_a.refresh_from_db()
        self.assertEqual(self.linha_a.status, LinhaMovel.Status.INATIVA)

        response = self.client.post(reverse(
            'estoque:reativar_linha_movel', args=[self.linha_a.pk],
        ))
        self.assertRedirects(response, reverse('estoque:lista_linhas_moveis'))
        self.linha_a.refresh_from_db()
        self.assertEqual(self.linha_a.status, LinhaMovel.Status.DISPONIVEL)

    def test_credenciais_exigem_permissao_dedicada_e_ficam_cifradas(self):
        self.login(self.admin_a)
        url = reverse('estoque:credenciais_linha_movel', args=[self.linha_a.pk])
        self.assertEqual(self.client.get(url).status_code, 403)

        self.admin_a.user_permissions.add(self.secret_permission)
        self.login(self.admin_a)
        key = Fernet.generate_key().decode('ascii')
        with override_settings(LINHAS_MOVEIS_CREDENTIAL_KEYS=[f'crud:{key}']):
            response = self.client.post(url, {
                'pin': '1234',
                'pin2': '',
                'puk': '87654321',
                'puk2': '',
            })

        self.assertRedirects(response, reverse('estoque:lista_linhas_moveis'))
        credencial = CredencialLinhaMovel.objects.get(linha=self.linha_a)
        self.assertNotIn('1234', credencial.conteudo_criptografado)
        self.assertNotIn('87654321', credencial.conteudo_criptografado)

    def test_credenciais_sem_chave_exibem_bloqueio_operacional(self):
        self.admin_a.user_permissions.add(self.secret_permission)
        self.login(self.admin_a)
        url = reverse('estoque:credenciais_linha_movel', args=[self.linha_a.pk])

        with override_settings(LINHAS_MOVEIS_CREDENTIAL_KEYS=[]):
            pagina = self.client.get(url)
            envio = self.client.post(url, {
                'pin': '1234',
                'pin2': '',
                'puk': '87654321',
                'puk2': '',
            })

        self.assertContains(pagina, 'LINHAS_MOVEIS_CREDENTIAL_KEYS')
        self.assertContains(pagina, 'disabled')
        self.assertEqual(envio.status_code, 200)
        self.assertFalse(CredencialLinhaMovel.objects.filter(linha=self.linha_a).exists())

    def test_credencial_de_outro_tenant_permanece_inacessivel(self):
        self.admin_a.user_permissions.add(self.secret_permission)
        self.login(self.admin_a)

        response = self.client.get(reverse(
            'estoque:credenciais_linha_movel', args=[self.linha_b.pk],
        ))

        self.assertEqual(response.status_code, 403)

    def test_rotas_estao_declaradas_no_gate_de_features(self):
        from estoque.tenant_feature_routes import TenantFeatureRoutePolicy

        nomes = {
            'lista_linhas_moveis', 'criar_linha_movel', 'editar_linha_movel',
            'inativar_linha_movel', 'reativar_linha_movel',
            'credenciais_linha_movel', 'operadoras_moveis',
            'editar_operadora_movel', 'alternar_operadora_movel',
        }
        declaradas = {
            nome for namespace, nome in TenantFeatureRoutePolicy.ROUTE_FEATURES
            if namespace == 'estoque'
        }
        self.assertTrue(nomes <= declaradas)
