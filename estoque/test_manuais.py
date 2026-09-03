from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from estoque.forms_documentacao import DriverImpressoraForm
from estoque.models import Base, DriverImpressora, Empresa, Equipamento, Produto
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

    def test_catalogo_de_manuais_e_exibido_em_espanhol(self):
        self.criar_equipamento(
            codigo='IMP-BR-XR',
            descricao='IMPRESSORA XEROX 3020',
            fabricante='Xerox',
            modelo='Phaser 3020',
            categoria='Impressoras',
        )
        self.user.perfil.idioma = 'es'
        self.user.perfil.save(update_fields=['idioma'])
        self.client.force_login(self.user)

        resposta = self.client.get(reverse('estoque:manuais'))

        self.assertContains(resposta, 'Manuales de equipos')
        self.assertContains(resposta, 'Guía del usuario de Phaser 3020')
        self.assertContains(resposta, 'Disponible localmente')


class DriversImpressorasTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin-drivers', password='segura-123'
        )
        self.admin.perfil.role = 'admin'
        self.admin.perfil.save()
        self.operador = User.objects.create_user(
            username='operador-drivers', password='segura-123'
        )
        self.url = reverse('estoque:drivers_impressoras')

    def tearDown(self):
        for driver in DriverImpressora.objects.all():
            if driver.arquivo and driver.arquivo.storage.exists(driver.arquivo.name):
                driver.arquivo.storage.delete(driver.arquivo.name)

    def test_admin_publica_e_usuario_baixa_driver_privado(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(self.url, {
            'titulo': 'Driver universal Xerox',
            'fabricante': 'Xerox',
            'modelo': 'Phaser 3020',
            'sistema_operacional': 'Windows 11',
            'arquitetura': '64 bits',
            'versao': '3.1',
            'descricao': 'Pacote validado pela equipe de suporte.',
            'instrucoes': 'Descompacte e execute o instalador.',
            'arquivo': SimpleUploadedFile(
                'xerox-3020.zip', b'conteudo-do-driver', content_type='application/zip'
            ),
        })
        self.assertRedirects(resposta, self.url)
        driver = DriverImpressora.objects.get()
        self.assertEqual(driver.nome_original, 'xerox-3020.zip')
        self.assertEqual(driver.tamanho_bytes, len(b'conteudo-do-driver'))
        self.assertEqual(driver.criado_por, self.admin)

        self.client.force_login(self.operador)
        pagina = self.client.get(self.url, {'q': 'Phaser'})
        self.assertContains(pagina, 'Phaser 3020')
        self.assertNotContains(pagina, 'Disponibilizar driver')
        download = self.client.get(reverse(
            'estoque:driver_impressora_arquivo', args=[driver.pk]
        ))
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download['X-Content-Type-Options'], 'nosniff')
        self.assertIn('attachment', download['Content-Disposition'])
        self.assertEqual(b''.join(download.streaming_content), b'conteudo-do-driver')

    def test_operador_nao_publica_e_admin_desativa(self):
        self.client.force_login(self.operador)
        negado = self.client.post(self.url, {
            'titulo': 'Envio indevido',
            'fabricante': 'HP',
            'modelo': 'Laser 107',
            'sistema_operacional': 'Windows 11',
            'arquivo': SimpleUploadedFile('driver.zip', b'zip'),
        })
        self.assertEqual(negado.status_code, 403)
        self.assertFalse(DriverImpressora.objects.exists())

        driver = DriverImpressora.objects.create(
            titulo='Driver HP', fabricante='HP', modelo='Laser 107',
            sistema_operacional='Windows 11', arquivo='arquivo.zip',
            nome_original='arquivo.zip', criado_por=self.admin,
        )
        self.client.force_login(self.admin)
        resposta = self.client.post(reverse(
            'estoque:driver_impressora_desativar', args=[driver.pk]
        ))
        self.assertRedirects(resposta, self.url)
        driver.refresh_from_db()
        self.assertFalse(driver.ativo)

    def test_rejeita_extensao_nao_permitida(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(self.url, {
            'titulo': 'Arquivo inválido',
            'fabricante': 'HP',
            'modelo': 'Laser 107',
            'sistema_operacional': 'Windows 11',
            'arquivo': SimpleUploadedFile('instrucoes.html', b'<html></html>'),
        })
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'EXE, MSI, ZIP, RAR, CAB ou INF')
        self.assertFalse(DriverImpressora.objects.exists())

    def test_aceita_rar_e_informa_limite_de_500_mb(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(self.url, {
            'titulo': 'Pacote compactado HP',
            'fabricante': 'HP',
            'modelo': 'LaserJet M111',
            'sistema_operacional': 'Windows 11',
            'arquivo': SimpleUploadedFile(
                'hp-m111.rar', b'conteudo-rar', content_type='application/vnd.rar'
            ),
        })

        self.assertRedirects(resposta, self.url)
        self.assertEqual(DriverImpressora.objects.get().nome_original, 'hp-m111.rar')
        pagina = self.client.get(self.url)
        self.assertContains(pagina, 'RAR')
        self.assertContains(pagina, '500 MB')

    def test_rejeita_driver_acima_de_500_mb_sem_carregar_arquivo_grande(self):
        arquivo = SimpleUploadedFile('driver.rar', b'conteudo')
        arquivo.size = 500 * 1024 * 1024 + 1
        form = DriverImpressoraForm(data={
            'titulo': 'Driver muito grande',
            'fabricante': 'HP',
            'modelo': 'LaserJet M111',
            'sistema_operacional': 'Windows 11',
        }, files={'arquivo': arquivo})

        self.assertFalse(form.is_valid())
        self.assertIn('no máximo 500 MB', ' '.join(form.errors['arquivo']))


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
