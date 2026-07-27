from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from estoque.models import Base, Empresa, Equipamento, Produto
from estoque.services.assistente_operacional_service import AssistenteOperacionalService
from estoque.services.manual_service import ManualService


class ManuaisViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='operador-manuais', password='segura-123')
        self.empresa = Empresa.objects.create(nome='Empresa teste')
        self.base = Base.objects.create(nome='Base teste', empresa=self.empresa)
        self.user.perfil.empresa = self.empresa
        self.user.perfil.save()
        self.user.perfil.regionais.add(self.base)

    def criar_equipamento(self, *, codigo, descricao, fabricante, modelo, categoria):
        produto = Produto.objects.create(
            codigo=codigo,
            descricao=descricao,
            fabricante=fabricante,
            modelo=modelo,
            categoria=categoria,
        )
        Equipamento.objects.create(
            produto=produto,
            numero_serie=f'SERIE-{codigo}',
            patrimonio=f'PAT-{codigo}',
            regional=self.base,
            codigo=f'EQP-{codigo}',
        )
        return produto

    def test_biblioteca_exige_login_e_aceita_operador(self):
        url = reverse('estoque:manuais')
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.user)
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Manuais de equipamentos')

    def test_pesquisa_filtra_por_modelo_cadastrado(self):
        self.criar_equipamento(
            codigo='ROT-BR-TP',
            descricao='ROUTER TP-LINK TL-WR829N',
            fabricante='TP-Link',
            modelo='TL-WR829N',
            categoria='Routers',
        )
        self.client.force_login(self.user)
        resposta = self.client.get(reverse('estoque:manuais'), {'q': 'WR829N'})
        self.assertContains(resposta, 'Guia de instalação rápida TL-WR829N')
        self.assertContains(resposta, 'Disponível localmente')
        self.assertContains(resposta, 'Firmware oficial')

    def test_todos_os_itens_possuem_acesso_a_driver_ou_software_oficial(self):
        for item in ManualService._dados_catalogo():
            with self.subTest(produto_codigo=item['produto_codigo']):
                self.assertTrue(item.get('driver_url', '').startswith('https://'))
                self.assertTrue(item.get('driver_label'))


class ToryManuaisTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='usuario-tory-manual', password='segura-123')

    def test_tory_localiza_manual_por_modelo(self):
        resposta = AssistenteOperacionalService.responder(
            self.user,
            'Tory, como resetar o roteador TL-WR829N?',
        )
        self.assertEqual(resposta['interpretacao']['intencao'], 'manuais')
        self.assertIn('TL-WR829N', resposta['resposta'])
        self.assertTrue(any(acao.get('url', '').endswith('.pdf') for acao in resposta['acoes']))

    def test_tory_entende_configuracao_do_ranger_sem_pedir_base(self):
        resposta = AssistenteOperacionalService.responder(
            self.user,
            'Me ajude com a configuração do Ranger 2k',
        )
        self.assertEqual(resposta['interpretacao']['intencao'], 'manuais')
        self.assertIn('Ranger 2K', resposta['resposta'])
        self.assertNotIn('qual base', resposta['resposta'].lower())

    def test_tory_entende_manuais_no_plural(self):
        resposta = AssistenteOperacionalService.responder(self.user, 'Manuais')
        self.assertEqual(resposta['interpretacao']['intencao'], 'manuais')
        self.assertIn('Informe o fabricante ou o modelo', resposta['resposta'])

    def test_tory_localiza_familia_hp_identificada(self):
        resposta = AssistenteOperacionalService.responder(
            self.user,
            'Qual é o manual da impressora HP Laser?',
        )
        self.assertEqual(resposta['interpretacao']['intencao'], 'manuais')
        self.assertIn('HP Laser série 100', resposta['resposta'])
        self.assertTrue(any(acao.get('url', '').endswith('.pdf') for acao in resposta['acoes']))

    def test_tory_localiza_manual_pantum_p2200_em_portugues(self):
        resposta = AssistenteOperacionalService.responder(
            self.user,
            'Preciso do manual da impressora Pantum P2200',
        )
        self.assertEqual(resposta['interpretacao']['intencao'], 'manuais')
        self.assertIn('Pantum P2200/P2500 Series V2.0', resposta['resposta'])
        self.assertIn('português', resposta['resposta'].lower())
        self.assertTrue(any(acao.get('url', '').endswith('.pdf') for acao in resposta['acoes']))

    def test_tory_localiza_guia_mc65_em_portugues(self):
        resposta = AssistenteOperacionalService.responder(
            self.user,
            'Como carregar a bateria do Motorola MC65?',
        )
        self.assertEqual(resposta['interpretacao']['intencao'], 'manuais')
        self.assertIn('MC65', resposta['resposta'])
        self.assertIn('português', resposta['resposta'].lower())
        self.assertTrue(any(acao.get('url', '').endswith('.pdf') for acao in resposta['acoes']))

    def test_tory_oferece_driver_oficial_da_pantum(self):
        resposta = AssistenteOperacionalService.responder(
            self.user,
            'Onde baixo o driver da Pantum P2200?',
        )
        self.assertEqual(resposta['interpretacao']['intencao'], 'drivers')
        self.assertIn('acesso oficial', resposta['resposta'].lower())
        self.assertTrue(any('pantum.com' in acao.get('url', '') for acao in resposta['acoes']))

    def test_pergunta_operacional_sem_modelo_nao_e_interceptada(self):
        self.assertIsNone(ManualService.tentar_responder('quantos equipamentos temos hoje?'))
