from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from compras.models import CapacidadeCatalogoProdutoEmpresa, CatalogoProdutoEmpresa
from estoque.models import (
    Base,
    CategoriaEquipamentoEmpresa,
    Empresa,
    Equipamento,
    Historico,
    HistoricoLinhaMovel,
    LinhaMovel,
    Modulo,
    ModuloEmpresa,
    OperadoraMovel,
    Perfil,
    Produto,
    VinculoLinhaEquipamento,
)
from estoque.services.linhas_moveis_service import LinhasMoveisService


class LinhaMovelCadastroEquipamentoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = Empresa.objects.create(nome='Empresa vínculo cadastro')
        cls.empresa_externa = Empresa.objects.create(nome='Empresa vínculo externa')
        cls.base = Base.objects.create(nome='Base vínculo cadastro', empresa=cls.empresa)
        cls.outra_base = Base.objects.create(nome='Outra Base vínculo', empresa=cls.empresa)
        cls.base_externa = Base.objects.create(
            nome='Base vínculo externa', empresa=cls.empresa_externa,
        )
        cls.admin = User.objects.create_user(
            'admin_vinculo_cadastro',
            password='senha-r1-segura',
        )
        Perfil.objects.update_or_create(
            user=cls.admin,
            defaults={'empresa': cls.empresa, 'role': Perfil.Role.ADMIN},
        )
        cls.gestor = User.objects.create_user('gestor_sem_chip', password='senha-gestor')
        perfil_gestor, _ = Perfil.objects.update_or_create(
            user=cls.gestor,
            defaults={'empresa': cls.empresa, 'role': Perfil.Role.GESTOR},
        )
        perfil_gestor.regionais.add(cls.base)
        for codigo, nome in (
            (Modulo.Codigo.EQUIPAMENTOS, 'Equipamentos'),
            (Modulo.Codigo.CADASTROS, 'Cadastros'),
            (Modulo.Codigo.CATALOGO, 'Catálogo'),
        ):
            modulo, _ = Modulo.objects.update_or_create(
                codigo=codigo,
                defaults={'nome': nome, 'ativo': True},
            )
            ModuloEmpresa.objects.update_or_create(
                empresa=cls.empresa,
                modulo=modulo,
                defaults={'habilitado': True},
            )

        cls.produto_movel = Produto.objects.create(
            codigo='PROD-VINCULO-MOVEL',
            descricao='Coletor com conectividade configurada',
            fabricante='Fabricante',
            modelo='Móvel',
            categoria='Coletores',
        )
        cls.produto_comum = Produto.objects.create(
            codigo='PROD-VINCULO-COMUM',
            descricao='Notebook sem conectividade',
            fabricante='Fabricante',
            modelo='Comum',
            categoria='Notebooks',
        )
        for categoria in ('Coletores', 'Notebooks'):
            CategoriaEquipamentoEmpresa.objects.create(
                empresa=cls.empresa,
                nome=categoria,
            )
        catalogo_movel = CatalogoProdutoEmpresa.objects.create(
            empresa=cls.empresa,
            produto=cls.produto_movel,
        )
        CatalogoProdutoEmpresa.objects.create(
            empresa=cls.empresa,
            produto=cls.produto_comum,
        )
        CapacidadeCatalogoProdutoEmpresa.objects.create(
            catalogo=catalogo_movel,
            codigo=CapacidadeCatalogoProdutoEmpresa.CONECTIVIDADE_MOVEL,
        )

        cls.operadora = OperadoraMovel.objects.create(
            empresa=cls.empresa,
            nome='Operadora vínculo',
        )
        cls.operadora_externa = OperadoraMovel.objects.create(
            empresa=cls.empresa_externa,
            nome='Operadora externa',
        )
        cls.linha = LinhaMovel.objects.create(
            empresa=cls.empresa,
            base=cls.base,
            numero_normalizado='+5511988881001',
            operadora=cls.operadora,
            iccid='8955012345678810001',
            criado_por=cls.admin,
        )
        cls.linha_outra_base = LinhaMovel.objects.create(
            empresa=cls.empresa,
            base=cls.outra_base,
            numero_normalizado='+5511988881002',
            operadora=cls.operadora,
            criado_por=cls.admin,
        )
        cls.linha_externa = LinhaMovel.objects.create(
            empresa=cls.empresa_externa,
            base=cls.base_externa,
            numero_normalizado='+5511988882001',
            operadora=cls.operadora_externa,
            iccid='8955012345678820001',
            criado_por=cls.admin,
        )

    def setUp(self):
        self.admin = User.objects.get(pk=self.admin.pk)
        self.client.force_login(self.admin)

    def payload(self, *, produto=None, linha=''):
        produto = produto or self.produto_movel
        return {
            'categoria': produto.categoria,
            'produto': produto.pk,
            'numero_serie': f'SERIE-R1D-{Equipamento.objects.count() + 1}',
            'patrimonio': f'PAT-R1D-{Equipamento.objects.count() + 1}',
            'regional': self.base.pk,
            'finalidade': Equipamento.Finalidade.OPERACIONAL,
            'responsavel': '',
            'linha_movel': linha,
        }

    def equipamento_existente(self, sufixo='EDIT'):
        return Equipamento.objects.create(
            produto=self.produto_movel,
            numero_serie=f'SERIE-R1E-{sufixo}',
            patrimonio=f'PAT-R1E-{sufixo}',
            regional=self.base,
            codigo=f'EQP-R1E-{sufixo}',
        )

    def test_endpoint_lista_apenas_linha_disponivel_da_mesma_base_e_tenant(self):
        response = self.client.get(reverse('estoque:linhas_moveis_disponiveis'), {
            'base': self.base.pk,
            'produto': self.produto_movel.pk,
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['habilitado'])
        self.assertEqual(
            [item['id'] for item in response.json()['linhas']],
            [self.linha.pk],
        )
        self.assertNotContains(response, self.linha.iccid)
        self.assertNotContains(response, self.linha_externa.numero_normalizado)

    def test_telas_de_linhas_moveis_renderizam_em_espanhol(self):
        self.admin.perfil.idioma = Perfil.Idioma.ES
        self.admin.perfil.save(update_fields=['idioma'])
        self.admin.user_permissions.add(Permission.objects.get(
            codename='visualizar_credenciais_linhas_moveis',
        ))

        lista = self.client.get(
            reverse('estoque:lista_linhas_moveis'),
        )
        cadastro = self.client.get(
            reverse('estoque:criar_linha_movel'),
        )
        operadoras = self.client.get(
            reverse('estoque:operadoras_moveis'),
        )
        credenciais = self.client.get(
            reverse('estoque:credenciais_linha_movel', args=[self.linha.pk]),
        )

        for response in (lista, cadastro, operadoras, credenciais):
            self.assertEqual(response.status_code, 200)
        self.assertContains(lista, 'Líneas móviles')
        self.assertContains(lista, 'Nuevo chip / línea')
        self.assertContains(cadastro, 'Activo móvil independiente')
        self.assertContains(operadoras, 'Operadoras móviles')
        self.assertContains(credenciais, 'Credenciales protegidas')

    def test_produto_sem_capacidade_nao_expoe_linhas(self):
        response = self.client.get(reverse('estoque:linhas_moveis_disponiveis'), {
            'base': self.base.pk,
            'produto': self.produto_comum.pk,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'habilitado': False, 'linhas': []})

    def test_cadastro_pode_vincular_linha_opcional_atomicamente(self):
        response = self.client.post(
            reverse('estoque:cadastrar_equipamento'),
            self.payload(linha=self.linha.pk),
        )

        self.assertRedirects(response, reverse('estoque:cadastrar_equipamento'))
        equipamento = Equipamento.objects.get(numero_serie='SERIE-R1D-1')
        vinculo = VinculoLinhaEquipamento.objects.get(
            equipamento=equipamento,
            fim_em__isnull=True,
        )
        self.assertEqual(vinculo.linha, self.linha)
        self.linha.refresh_from_db()
        self.assertEqual(self.linha.status, LinhaMovel.Status.EM_USO)
        self.assertTrue(self.linha.historico.filter(
            evento=HistoricoLinhaMovel.Evento.VINCULO,
        ).exists())
        self.assertEqual(
            Historico.objects.get(equipamento=equipamento).detalhes['linha_movel_id'],
            self.linha.pk,
        )

    def test_chip_permanece_ativo_independente_sem_equipamento(self):
        response = self.client.post(
            reverse('estoque:cadastrar_equipamento'),
            self.payload(linha=''),
        )

        self.assertRedirects(response, reverse('estoque:cadastrar_equipamento'))
        self.linha.refresh_from_db()
        self.assertEqual(self.linha.status, LinhaMovel.Status.DISPONIVEL)
        self.assertFalse(
            VinculoLinhaEquipamento.objects.filter(linha=self.linha).exists()
        )

    def test_linha_forjada_em_produto_sem_capacidade_e_rejeitada(self):
        response = self.client.post(
            reverse('estoque:cadastrar_equipamento'),
            self.payload(produto=self.produto_comum, linha=self.linha.pk),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Equipamento.objects.filter(numero_serie='SERIE-R1D-1').exists()
        )
        self.assertIn('linha_movel', response.context['form'].errors)

    @patch('estoque.services.linhas_moveis_service.LinhasMoveisService.vincular')
    def test_falha_no_vinculo_desfaz_cadastro_do_equipamento(self, vincular):
        vincular.side_effect = ValidationError('Conflito concorrente no vínculo.')

        response = self.client.post(
            reverse('estoque:cadastrar_equipamento'),
            self.payload(linha=self.linha.pk),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Equipamento.objects.filter(numero_serie='SERIE-R1D-1').exists()
        )
        self.assertIn('linha_movel', response.context['form'].errors)

    def test_edicao_exibe_e_permite_vincular_chip_disponivel(self):
        equipamento = self.equipamento_existente()
        editar = self.client.get(reverse(
            'estoque:editar_equipamento', args=[equipamento.pk],
        ))
        self.assertContains(editar, 'Conectividade móvel')
        self.assertContains(editar, self.linha.numero_formatado)
        self.assertContains(editar, 'O vínculo é feito abaixo')
        self.assertContains(editar, 'Vincular linha')

        response = self.client.post(reverse(
            'estoque:atualizar_linha_movel_equipamento', args=[equipamento.pk],
        ), {
            'acao_linha_movel': 'vincular',
            'linha_movel': self.linha.pk,
            'senha_confirmacao': 'senha-r1-segura',
        })

        self.assertRedirects(
            response,
            reverse('estoque:editar_equipamento', args=[equipamento.pk]),
        )
        self.assertTrue(VinculoLinhaEquipamento.objects.filter(
            equipamento=equipamento,
            linha=self.linha,
            fim_em__isnull=True,
        ).exists())

    def test_edicao_troca_e_desvincula_sem_apagar_historico(self):
        equipamento = self.equipamento_existente('TROCA')
        outra_linha = LinhaMovel.objects.create(
            empresa=self.empresa,
            base=self.base,
            numero_normalizado='+5511988881099',
            operadora=self.operadora,
            criado_por=self.admin,
        )
        primeiro = LinhasMoveisService.vincular(
            usuario=self.admin,
            linha_id=self.linha.pk,
            equipamento_id=equipamento.pk,
        )

        troca = self.client.post(reverse(
            'estoque:atualizar_linha_movel_equipamento', args=[equipamento.pk],
        ), {
            'acao_linha_movel': 'trocar',
            'linha_movel': outra_linha.pk,
            'motivo_linha_movel': 'Troca de operadora',
            'senha_confirmacao': 'senha-r1-segura',
        })
        self.assertEqual(troca.status_code, 302)
        primeiro.refresh_from_db()
        self.assertIsNotNone(primeiro.fim_em)

        desvinculo = self.client.post(reverse(
            'estoque:atualizar_linha_movel_equipamento', args=[equipamento.pk],
        ), {
            'acao_linha_movel': 'desvincular',
            'motivo_linha_movel': 'Retirada do chip',
            'senha_confirmacao': 'senha-r1-segura',
        })
        self.assertEqual(desvinculo.status_code, 302)
        self.assertFalse(VinculoLinhaEquipamento.objects.filter(
            equipamento=equipamento,
            fim_em__isnull=True,
        ).exists())
        self.assertEqual(
            VinculoLinhaEquipamento.objects.filter(equipamento=equipamento).count(),
            2,
        )

    def test_ficha_modal_exibe_conectividade_e_linha_do_tempo_sem_iccid(self):
        equipamento = self.equipamento_existente('FICHA')
        linha_anterior = LinhaMovel.objects.create(
            empresa=self.empresa,
            base=self.base,
            numero_normalizado='+5511988881088',
            operadora=self.operadora,
            iccid='8955012345678810088',
            criado_por=self.admin,
        )
        LinhasMoveisService.vincular(
            usuario=self.admin,
            linha_id=linha_anterior.pk,
            equipamento_id=equipamento.pk,
        )
        LinhasMoveisService.trocar(
            usuario=self.admin,
            equipamento_id=equipamento.pk,
            nova_linha_id=self.linha.pk,
            motivo='Troca registrada na ficha',
        )
        historico = Historico.objects.create(
            equipamento=equipamento,
            tipo_acao='EDICAO',
            usuario=self.admin,
            detalhes={'mensagem': 'Ficha R1.F'},
        )

        response = self.client.get(reverse(
            'estoque:historico_modal', args=[equipamento.pk],
        ))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Conectividade móvel')
        self.assertContains(response, self.linha.numero_formatado)
        self.assertContains(response, linha_anterior.numero_formatado)
        self.assertContains(response, 'TROCA REGISTRADA NA FICHA')
        self.assertNotContains(response, linha_anterior.iccid)

        detalhe = self.client.get(reverse(
            'estoque:historico_detalhes', args=[historico.pk],
        ))
        self.assertEqual(detalhe.status_code, 200)
        self.assertContains(detalhe, 'Conectividade móvel')
        self.assertContains(detalhe, linha_anterior.numero_formatado)
        self.assertNotContains(detalhe, linha_anterior.iccid)

    def test_modal_admin_exibe_opcao_de_vinculo_e_gestor_nao_ve_informacoes(self):
        equipamento = self.equipamento_existente('MODAL-VINCULO')
        Historico.objects.create(
            equipamento=equipamento,
            tipo_acao='CRIACAO',
            usuario=self.admin,
            detalhes={'mensagem': 'Modal vínculo'},
        )
        segunda_linha = LinhaMovel.objects.create(
            empresa=self.empresa,
            base=self.base,
            numero_normalizado='+5511988881077',
            operadora=self.operadora,
            criado_por=self.admin,
        )

        admin_response = self.client.get(reverse(
            'estoque:historico_modal', args=[equipamento.pk],
        ))
        self.assertContains(admin_response, 'Vincular linha')
        self.assertContains(admin_response, self.linha.numero_formatado)
        self.assertContains(admin_response, segunda_linha.numero_formatado)

        self.client.force_login(User.objects.get(pk=self.gestor.pk))
        gestor_response = self.client.get(reverse(
            'estoque:historico_modal', args=[equipamento.pk],
        ))
        self.assertEqual(gestor_response.status_code, 200)
        self.assertNotContains(gestor_response, 'Conectividade móvel')
        self.assertNotContains(gestor_response, self.linha.numero_formatado)
        self.assertNotContains(gestor_response, segunda_linha.numero_formatado)

    def test_gestor_nao_ve_chip_no_cadastro_nem_nas_opcoes_do_catalogo(self):
        produto_chip = Produto.objects.create(
            codigo='CHIP-OCULTO-GESTOR',
            descricao='CHIP CONFIDENCIAL GESTOR',
            fabricante='Operadora',
            modelo='SIM',
            categoria='Chips',
        )
        catalogo_chip = CatalogoProdutoEmpresa.objects.create(
            empresa=self.empresa,
            produto=produto_chip,
            ativo=True,
        )
        CapacidadeCatalogoProdutoEmpresa.objects.create(
            catalogo=catalogo_chip,
            codigo=CapacidadeCatalogoProdutoEmpresa.ATIVO_LINHA_MOVEL,
            ativa=True,
        )
        gestor = User.objects.get(pk=self.gestor.pk)
        gestor.user_permissions.add(Permission.objects.get(
            codename='cadastrar_equipamentos',
        ))
        self.client.force_login(gestor)

        cadastro = self.client.get(reverse('estoque:cadastrar_equipamento'))
        catalogo = self.client.get(reverse('compras:catalogo_empresa'))

        self.assertEqual(cadastro.status_code, 200)
        self.assertNotContains(cadastro, 'Chip / linha móvel')
        self.assertNotContains(cadastro, 'Ir para cadastro de chip')
        self.assertNotContains(cadastro, 'Conectividade móvel opcional')
        self.assertEqual(catalogo.status_code, 200)
        self.assertNotContains(catalogo, 'CHIP CONFIDENCIAL GESTOR')
        self.assertNotContains(catalogo, 'Equipamentos que aceitam chip')
        self.assertNotContains(catalogo, 'Produtos que representam chip')

        resposta = self.client.post(reverse('compras:catalogo_empresa'), {
            'empresa': self.empresa.pk,
            'produtos': [self.produto_movel.pk, self.produto_comum.pk],
            'produtos_chip_independente': [produto_chip.pk],
        })
        self.assertEqual(resposta.status_code, 302)
        catalogo_chip.refresh_from_db()
        self.assertTrue(catalogo_chip.ativo)
        self.assertTrue(catalogo_chip.capacidades.filter(
            codigo=CapacidadeCatalogoProdutoEmpresa.ATIVO_LINHA_MOVEL,
            ativa=True,
        ).exists())

    def test_superuser_com_perfil_nao_admin_pode_vincular_no_equipamento(self):
        equipamento = self.equipamento_existente('SUPERUSER')
        Historico.objects.create(
            equipamento=equipamento,
            tipo_acao='CRIACAO',
            usuario=self.admin,
            detalhes={'mensagem': 'Modal superuser'},
        )
        self.admin.is_superuser = True
        self.admin.is_staff = True
        self.admin.save(update_fields=['is_superuser', 'is_staff'])
        Perfil.objects.filter(user=self.admin).update(role=Perfil.Role.GESTOR)
        self.client.force_login(self.admin)

        edicao = self.client.get(reverse(
            'estoque:editar_equipamento', args=[equipamento.pk],
        ))
        modal = self.client.get(reverse(
            'estoque:historico_modal', args=[equipamento.pk],
        ))

        self.assertEqual(edicao.status_code, 200)
        self.assertContains(edicao, 'Vincular linha')
        self.assertContains(edicao, self.linha.numero_formatado)
        self.assertEqual(modal.status_code, 200)
        self.assertContains(modal, 'Vincular linha')
        self.assertContains(modal, self.linha.numero_formatado)

    def test_templates_de_cadastro_explicam_ativo_independente_e_vinculo_opcional(self):
        equipamento = self.client.get(reverse('estoque:cadastrar_equipamento'), {
            'regional': self.base.pk,
        })
        chip = self.client.get(reverse('estoque:criar_linha_movel'))

        self.assertContains(equipamento, 'associe uma linha móvel disponível')
        self.assertContains(chip, 'Ativo móvel independente')
        self.assertContains(chip, 'não exige equipamento')

    def test_catalogo_separa_equipamento_vinculavel_de_chip_independente(self):
        response = self.client.post(reverse('compras:catalogo_empresa'), {
            'empresa': self.empresa.pk,
            'produtos': [self.produto_movel.pk, self.produto_comum.pk],
            'produtos_conectividade_movel': [self.produto_movel.pk],
            'produtos_chip_independente': [self.produto_comum.pk],
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(CapacidadeCatalogoProdutoEmpresa.objects.filter(
            catalogo__empresa=self.empresa,
            catalogo__produto=self.produto_comum,
            codigo=CapacidadeCatalogoProdutoEmpresa.ATIVO_LINHA_MOVEL,
            ativa=True,
        ).exists())
        produtos = self.client.get(reverse('estoque:produtos_por_categoria'), {
            'base': self.base.pk,
            'categoria': self.produto_comum.categoria,
        })
        self.assertEqual(produtos.status_code, 200)
        self.assertNotIn(
            self.produto_comum.pk,
            [item['id'] for item in produtos.json()['produtos']],
        )
        cadastro = self.client.get(reverse('estoque:cadastrar_equipamento'), {
            'regional': self.base.pk,
        })
        self.assertContains(cadastro, 'Ir para cadastro de chip')
        categorias = dict(cadastro.context['form'].fields['categoria'].choices)
        self.assertNotIn(self.produto_comum.categoria, categorias)
        self.assertIn(self.produto_movel.categoria, categorias)
