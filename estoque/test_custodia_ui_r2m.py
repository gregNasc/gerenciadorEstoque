from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from compras.models import (
    CapacidadeCatalogoProdutoEmpresa,
    CatalogoProdutoEmpresa,
)
from estoque.models import (
    Base,
    Colaborador,
    Custodia,
    DevolucaoCustodia,
    Empresa,
    Equipamento,
    ItemCustodia,
    ItemDevolucaoCustodia,
    Perfil,
    Produto,
)
from estoque.policies.custodias import CustodiaAccessPolicy


class CustodiaInterfaceR2MTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = Empresa.objects.create(nome='Empresa Custódia UI')
        cls.outra_empresa = Empresa.objects.create(nome='Empresa Oculta Custódia UI')
        cls.base = Base.objects.create(nome='Base Custódia UI', empresa=cls.empresa)
        cls.outra_base = Base.objects.create(nome='Base Oculta', empresa=cls.outra_empresa)

        cls.admin = User.objects.create_user('admin.custodia.ui', password='senha')
        cls.gestor = User.objects.create_user('gestor.custodia.ui', password='senha')
        cls.operador = User.objects.create_user('operador.custodia.ui', password='senha')
        cls.jose = User.objects.create_user('jose.barboza', password='senha')
        for usuario, role in (
            (cls.admin, Perfil.Role.ADMIN),
            (cls.gestor, Perfil.Role.GESTOR),
            (cls.operador, Perfil.Role.OPERADOR),
            (cls.jose, Perfil.Role.ADMIN),
        ):
            usuario.perfil.empresa = cls.empresa
            usuario.perfil.role = role
            usuario.perfil.save(update_fields=['empresa', 'role'])
        cls.gestor.perfil.regionais.add(cls.base)
        cls.operador.perfil.regionais.add(cls.base)

        cls.usuario_colaborador = User.objects.create_user(
            'colaborador.com.login',
            first_name='Pessoa',
            last_name='Com Login',
            email='pessoa@example.com',
        )
        cls.usuario_colaborador.perfil.empresa = cls.empresa
        cls.usuario_colaborador.perfil.role = Perfil.Role.OPERADOR
        cls.usuario_colaborador.perfil.save(update_fields=['empresa', 'role'])
        cls.colaborador_sem_login = Colaborador.objects.create(
            empresa=cls.empresa,
            base=cls.base,
            nome='Pessoa Sem Login',
        )
        cls.colaborador_oculto = Colaborador.objects.create(
            empresa=cls.outra_empresa,
            base=cls.outra_base,
            nome='Pessoa de Outro Tenant',
        )

        cls.produto = Produto.objects.create(
            codigo='NOTE-CUSTODIA-UI',
            descricao='Notebook Custódia UI',
            fabricante='Teste',
            modelo='UI',
            categoria='Notebook',
        )
        catalogo = CatalogoProdutoEmpresa.objects.create(
            empresa=cls.empresa,
            produto=cls.produto,
            ativo=True,
        )
        CapacidadeCatalogoProdutoEmpresa.objects.create(
            catalogo=catalogo,
            codigo=CapacidadeCatalogoProdutoEmpresa.CUSTODIA_PESSOAL,
            ativa=True,
        )
        cls.equipamento = Equipamento.objects.create(
            produto=cls.produto,
            numero_serie='SERIE-CUSTODIA-UI',
            patrimonio='PAT-CUSTODIA-UI',
            regional=cls.base,
            codigo='EQ-CUSTODIA-UI',
        )

    def test_apenas_superuser_e_admin_visualizam_modulo(self):
        self.assertTrue(CustodiaAccessPolicy.permite(self.admin))
        self.assertFalse(CustodiaAccessPolicy.permite(self.gestor))
        self.assertFalse(CustodiaAccessPolicy.permite(self.operador))
        for usuario in (self.gestor, self.operador):
            self.client.force_login(usuario)
            self.assertEqual(
                self.client.get(reverse('estoque:lista_custodias')).status_code,
                403,
            )

    def test_jose_nao_acessa_custodia(self):
        self.assertFalse(CustodiaAccessPolicy.permite(
            self.jose,
            CustodiaAccessPolicy.VIEW,
        ))
        self.assertFalse(CustodiaAccessPolicy.permite(
            self.jose,
            CustodiaAccessPolicy.MANAGE,
        ))
        self.client.force_login(self.jose)
        self.assertEqual(self.client.get(reverse('estoque:lista_custodias')).status_code, 403)
        self.assertEqual(self.client.get(reverse('estoque:criar_custodia')).status_code, 403)
        self.assertEqual(self.client.get(reverse('estoque:criar_colaborador')).status_code, 403)

    def test_admin_ve_dropdown_e_nao_enxerga_outro_tenant(self):
        self.client.force_login(self.admin)
        resposta = self.client.get(reverse('estoque:lista_colaboradores'))
        self.assertContains(resposta, 'Custódia')
        self.assertContains(resposta, self.colaborador_sem_login.nome)
        self.assertNotContains(resposta, self.colaborador_oculto.nome)

    def test_cadastra_colaborador_com_usuario_existente(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(reverse('estoque:criar_colaborador'), {
            'empresa': self.empresa.pk,
            'base': self.base.pk,
            'usuario': self.usuario_colaborador.pk,
            'nome': '',
            'email': '',
            'telefone': '',
            'matricula': 'MAT-LOGIN',
            'cargo_funcao': '',
            'setor': '',
            'ativo': 'on',
        })
        self.assertRedirects(resposta, reverse('estoque:lista_colaboradores'))
        colaborador = Colaborador.objects.get(usuario=self.usuario_colaborador)
        self.assertEqual(colaborador.nome.casefold(), 'pessoa com login')
        self.assertEqual(colaborador.email, 'pessoa@example.com')

    def test_cadastra_colaborador_sem_acesso(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(reverse('estoque:criar_colaborador'), {
            'empresa': self.empresa.pk,
            'base': self.base.pk,
            'usuario': '',
            'nome': 'Colaborador Operacional',
            'email': 'operacional@example.com',
            'telefone': '',
            'matricula': 'MAT-SEM-LOGIN',
            'cargo_funcao': '',
            'setor': '',
            'ativo': 'on',
        })
        self.assertRedirects(resposta, reverse('estoque:lista_colaboradores'))
        colaborador = Colaborador.objects.get(matricula='MAT-SEM-LOGIN')
        self.assertIsNone(colaborador.usuario)

    def test_admin_cria_custodia_e_vincula_equipamento(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(reverse('estoque:criar_custodia'), {
            'empresa': self.empresa.pk,
            'base': self.base.pk,
            'colaborador': self.colaborador_sem_login.pk,
            'local_fisico': '',
            'data_entrega': '2026-10-15',
            'condicao_geral': Custodia.CondicaoGeral.BOM,
            'modalidade_custodiante': Custodia.ModalidadeCustodiante.COLABORADOR,
            'razao_social_responsavel': 'Inventory Teste Ltda.',
            'cnpj_responsavel': '12.345.678/0001-90',
            'custodiante_cpf': '123.456.789-00',
            'custodiante_identificacao': 'MAT-SEM-LOGIN',
            'custodiante_funcao_atividade': 'Operação',
            'custodiante_email': 'operacional@example.com',
            'empresa_contratada': '',
            'cnpj_contratada': '',
            'responsavel_entrega_nome': 'Admin Custódia',
            'testemunha_1_nome': 'Testemunha RH',
            'testemunha_1_cpf': '111.222.333-44',
            'testemunha_1_email': 'rh@example.com',
            'testemunha_2_nome': 'Testemunha Operacional',
            'testemunha_2_cpf': '555.666.777-88',
            'testemunha_2_email': 'testemunha@example.com',
            'observacao': 'Entrega controlada',
            'equipamentos': [self.equipamento.pk],
            'linhas_moveis': [],
        })
        custodia = Custodia.objects.get(colaborador=self.colaborador_sem_login)
        self.assertRedirects(
            resposta,
            reverse('estoque:detalhe_custodia', args=[custodia.pk]),
        )
        self.assertEqual(custodia.status, Custodia.Status.ATIVA)
        self.assertEqual(custodia.itens.get().equipamento, self.equipamento)
        self.assertTrue(hasattr(custodia, 'termo_entrega'))
        self.equipamento.refresh_from_db()
        self.assertEqual(self.equipamento.responsavel, self.colaborador_sem_login.nome)

    def test_admin_nao_configura_catalogo_restrito_ao_superadmin(self):
        capacidade = CapacidadeCatalogoProdutoEmpresa.objects.get(
            catalogo__empresa=self.empresa,
            catalogo__produto=self.produto,
            codigo=CapacidadeCatalogoProdutoEmpresa.CUSTODIA_PESSOAL,
        )
        capacidade.delete()

        self.client.force_login(self.admin)
        resposta = self.client.post(reverse('compras:catalogo_empresa'), {
            'empresa': self.empresa.pk,
            'produtos': [self.produto.pk],
            'produtos_custodia': [self.produto.pk],
            'produtos_conectividade_movel': [],
            'produtos_chip_independente': [],
        })

        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(
            CapacidadeCatalogoProdutoEmpresa.objects.filter(
                catalogo__empresa=self.empresa,
                catalogo__produto=self.produto,
                codigo=CapacidadeCatalogoProdutoEmpresa.CUSTODIA_PESSOAL,
            ).exists()
        )
        resposta_custodia = self.client.get(reverse('estoque:criar_custodia'))
        self.assertContains(
            resposta_custodia,
            f'data-base-id="{self.base.pk}"',
            html=False,
        )
        self.assertContains(
            resposta_custodia,
            f'value="{self.equipamento.pk}"',
            html=False,
        )

    def test_seletor_de_custodia_identifica_a_base_de_cada_equipamento(self):
        self.client.force_login(self.admin)

        resposta = self.client.get(reverse('estoque:criar_custodia'))

        self.assertContains(
            resposta,
            f'data-base-id="{self.base.pk}"',
            html=False,
        )
        self.assertContains(resposta, 'id="custodia-filtro-categoria"', html=False)
        self.assertContains(resposta, 'id="custodia-filtro-equipamento"', html=False)
        self.assertContains(resposta, 'data-categoria="Notebook"', html=False)
        self.assertContains(resposta, 'data-patrimonio="PAT-CUSTODIA-UI"', html=False)
        self.assertContains(resposta, 'data-numero-serie="SERIE-CUSTODIA-UI"', html=False)
        self.assertContains(resposta, 'Empresa responsável pelos ativos')
        self.assertContains(resposta, 'Empresa do colaborador ou prestador')
        self.assertContains(resposta, 'id="id_empresa_contratada"', html=False)
        self.assertContains(resposta, 'por exemplo AJN')
        self.assertContains(resposta, 'custodia-sem-equipamentos')

    def test_admin_registra_devolucao_e_libera_equipamento(self):
        custodia = Custodia.objects.create(
            empresa=self.empresa,
            base=self.base,
            colaborador=self.colaborador_sem_login,
            registrado_por=self.admin,
            status=Custodia.Status.RASCUNHO,
            data_entrega=date(2026, 10, 15),
        )
        item = ItemCustodia.objects.create(
            custodia=custodia,
            equipamento=self.equipamento,
            condicao_entrega=Custodia.CondicaoGeral.BOM,
        )
        custodia.status = Custodia.Status.ATIVA
        custodia.save(update_fields=['status', 'atualizado_em'])
        self.client.force_login(self.admin)
        resposta = self.client.post(reverse('estoque:devolver_custodia', args=[custodia.pk]), {
            'data_devolucao': '2026-10-15T15:30',
            'motivo': 'Encerramento do vínculo',
            'responsavel_recebimento': self.colaborador_sem_login.pk,
            'responsavel_recebimento_email': 'operacional@example.com',
            'resultado_conferencia': DevolucaoCustodia.ResultadoConferencia.COMPLETA,
            'pendencias': '',
            'testemunha_1_nome': 'Testemunha RH',
            'testemunha_1_cpf': '111.222.333-44',
            'testemunha_1_email': 'rh@example.com',
            'testemunha_2_nome': 'Testemunha Operacional',
            'testemunha_2_cpf': '555.666.777-88',
            'testemunha_2_email': 'testemunha@example.com',
            'observacao': 'Recebido em conferência',
            f'situacao_{item.pk}': ItemDevolucaoCustodia.Situacao.DEVOLVIDO,
            f'condicao_{item.pk}': Custodia.CondicaoGeral.BOM,
            f'observacao_{item.pk}': 'Sem avarias',
            f'acessorios_{item.pk}': 'Fonte e cabo',
        })
        self.assertRedirects(
            resposta,
            reverse('estoque:detalhe_custodia', args=[custodia.pk]),
        )
        custodia.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(custodia.status, Custodia.Status.FINALIZADA)
        self.assertFalse(item.vigente)
        self.assertIsNotNone(item.devolvido_em)
        self.assertTrue(hasattr(custodia.devolucoes.get(), 'termo_devolucao'))
