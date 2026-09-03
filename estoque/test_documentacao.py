import io
import tempfile
import zipfile

from django.contrib.auth.models import Permission, User
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from estoque.models import Base, Empresa, ResolucaoDocumento, VideoDocumentacao
from estoque.services.assistente_operacional_service import AssistenteOperacionalService
from estoque.services.documentation_service import DocumentationService
from insumos.models import (
    Cliente,
    ClienteChecklistDocumento,
    ClienteRelatorio,
    Inventario,
    TipoRelatorioCliente,
)


def _docx_minimo(texto):
    buffer = io.BytesIO()
    documento_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body><w:p><w:r><w:t>{texto}</w:t></w:r></w:p></w:body>'
        '</w:document>'
    )
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as pacote:
        pacote.writestr('word/document.xml', documento_xml)
    return buffer.getvalue()


class DocumentationServiceTests(TestCase):
    def test_catalogo_tem_procedimentos_locais_em_portugues_e_espanhol(self):
        resolucoes = DocumentationService.listar(tipo='RESOLUCAO')
        self.assertEqual(len(resolucoes), 24)
        self.assertTrue(all(item['arquivo_disponivel'] for item in resolucoes))
        self.assertTrue(all(item['arquivo_url'].endswith('.pdf') for item in resolucoes))
        self.assertTrue(DocumentationService.listar(termo='Skorpio X4'))
        self.assertTrue(DocumentationService.listar(termo='MobyData M52'))
        resolucoes_es = DocumentationService.listar(tipo='RESOLUCAO', idioma='es')
        self.assertEqual(len(resolucoes_es), 11)
        self.assertTrue(any(item['modelo'] == 'LaserJet M111' for item in resolucoes_es))
        self.assertTrue(all(item['idioma_codigo'] == 'es' for item in resolucoes_es))

    def test_pesquisa_por_modelo_sintoma_e_driver_retorna_tipos_corretos(self):
        tipos_m2020 = {
            item['tipo_documento'] for item in DocumentationService.listar(termo='M2020')
        }
        self.assertIn('MANUAL_OFICIAL', tipos_m2020)
        self.assertIn('RESOLUCAO', tipos_m2020)
        self.assertTrue(all(
            item['tipo_documento'] == 'RESOLUCAO'
            for item in DocumentationService.listar(termo='código 43')
        ))
        self.assertTrue(DocumentationService.listar(termo='toner', tipo='RESOLUCAO'))
        self.assertTrue(DocumentationService.listar(termo='driver', tipo='MANUAL_OFICIAL'))

    def test_arquivo_inexistente_nao_produz_url(self):
        item = DocumentationService._preparar_item({
            'tipo_documento': 'RESOLUCAO',
            'arquivo': 'documentacao/resolucao/inexistente.pdf',
        })
        self.assertFalse(item['arquivo_disponivel'])
        self.assertEqual(item['arquivo_url'], '')

    def test_caminho_de_arquivo_nao_pode_escapar_da_pasta_estatica(self):
        item = DocumentationService._preparar_item({
            'tipo_documento': 'RESOLUCAO',
            'arquivo': '../data/documentacao.json',
        })
        self.assertFalse(item['arquivo_disponivel'])
        self.assertEqual(item['arquivo_url'], '')


class DocumentationViewsTests(TestCase):
    def setUp(self):
        self.diretorio_temporario = tempfile.TemporaryDirectory()
        self.campo_arquivo = ClienteChecklistDocumento._meta.get_field('arquivo')
        self.storage_original = self.campo_arquivo.storage
        self.campo_arquivo.storage = FileSystemStorage(
            location=self.diretorio_temporario.name
        )
        self.campo_resolucao = ResolucaoDocumento._meta.get_field('arquivo')
        self.storage_resolucao_original = self.campo_resolucao.storage
        self.campo_resolucao.storage = FileSystemStorage(
            location=self.diretorio_temporario.name
        )
        self.user = User.objects.create_user(username='operador-documentacao', password='segura-123')
        self.empresa = Empresa.objects.create(nome='Empresa documentação')
        self.base = Base.objects.create(nome='Base documentação', empresa=self.empresa)
        self.user.perfil.empresa = self.empresa
        self.user.perfil.role = 'operador'
        self.user.perfil.save()
        self.user.perfil.regionais.add(self.base)

    def tearDown(self):
        self.campo_arquivo.storage = self.storage_original
        self.campo_resolucao.storage = self.storage_resolucao_original
        self.diretorio_temporario.cleanup()
        super().tearDown()

    def test_central_exige_login_e_dropdown_aparece_para_usuario(self):
        url = reverse('estoque:documentacao')
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.user)
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Central de Documentação')
        self.assertContains(resposta, 'documentacaoDropdown')
        self.assertContains(resposta, 'Resolução de problemas')

    def test_filtro_de_tipo_e_links_pdf_seguros(self):
        self.client.force_login(self.user)
        resposta = self.client.get(reverse('estoque:documentacao'), {'tipo': 'RESOLUCAO'})
        self.assertContains(resposta, 'Xerox Phaser 3020 - Guia interno')
        self.assertNotContains(resposta, 'Guia do usuário Phaser 3020')
        self.assertContains(resposta, 'target="_blank"')
        self.assertContains(resposta, 'rel="noopener noreferrer"')
        videos_negado = self.client.post(reverse('estoque:documentacao_videos'), {
            'titulo': 'Vídeo não autorizado',
            'url': 'https://example.com/video',
            'origem': 'INTERNO',
        })
        self.assertEqual(videos_negado.status_code, 403)

    def test_checklist_clientes_respeita_escopo_das_bases(self):
        cliente_permitido = Cliente.objects.create(sigla='OK', nome='Cliente permitido')
        cliente_fora = Cliente.objects.create(sigla='FORA', nome='Cliente fora do escopo')
        outra_empresa = Empresa.objects.create(nome='Outra empresa')
        outra_base = Base.objects.create(nome='Outra base', empresa=outra_empresa)
        self.user.perfil.regionais.add(outra_base)
        ClienteChecklistDocumento.objects.create(
            cliente=cliente_permitido,
            arquivo=SimpleUploadedFile(
                'checklist-cliente.pdf',
                b'%PDF-1.4 checklist',
                content_type='application/pdf',
            ),
            nome_original='checklist-cliente.pdf',
            enviado_por=self.user,
        )
        Inventario.objects.create(
            cliente=cliente_permitido, loja='Loja 1', base=self.base,
            data_inicio='2026-08-20', criado_por=self.user,
        )
        Inventario.objects.create(
            cliente=cliente_fora, loja='Loja 2', base=outra_base,
            data_inicio='2026-08-20', criado_por=self.user,
        )
        self.client.force_login(self.user)
        resposta = self.client.get(reverse('estoque:documentacao_clientes'))
        self.assertContains(resposta, 'CLIENTE PERMITIDO')
        self.assertContains(resposta, 'checklist-cliente.pdf')
        self.assertContains(resposta, 'Visualizar')
        self.assertContains(resposta, 'Baixar')
        self.assertNotContains(resposta, 'CLIENTE FORA DO ESCOPO')
        busca_global = self.client.get(reverse('estoque:documentacao'), {'q': 'OK'})
        self.assertContains(busca_global, 'Checklist de entregáveis')
        self.assertContains(busca_global, 'checklist-cliente.pdf')
        self.assertNotContains(busca_global, 'CLIENTE FORA DO ESCOPO')
        resposta_tory = AssistenteOperacionalService.responder(
            self.user, 'Tory, o que entregamos para o cliente OK?'
        )
        self.assertEqual(resposta_tory['contexto']['tipo_documento'], 'CHECKLIST_CLIENTE')
        self.assertIn('checklist-cliente.pdf', resposta_tory['resposta'])

        detalhe = self.client.get(
            reverse('estoque:documentacao_cliente_detalhe', args=[cliente_permitido.pk])
        )
        self.assertEqual(detalhe.status_code, 200)
        self.assertContains(detalhe, 'checklist-cliente.pdf')
        self.assertContains(detalhe, 'Visualizar sem baixar')
        self.assertContains(detalhe, 'app-document-viewer-frame')
        self.assertContains(detalhe, '?download=1')
        self.assertNotContains(detalhe, 'id_arquivo')
        negado = self.client.post(
            reverse('estoque:documentacao_cliente_detalhe', args=[cliente_permitido.pk]),
            {'arquivo': SimpleUploadedFile('outro.pdf', b'%PDF-1.4 outro')},
        )
        self.assertEqual(negado.status_code, 403)

        arquivo_url = reverse(
            'estoque:documentacao_cliente_arquivo', args=[cliente_permitido.pk]
        )
        arquivo = self.client.get(arquivo_url)
        self.assertEqual(arquivo.status_code, 200)
        self.assertIn('inline', arquivo['Content-Disposition'])
        self.assertEqual(arquivo['X-Frame-Options'], 'SAMEORIGIN')
        self.assertEqual(b''.join(arquivo.streaming_content), b'%PDF-1.4 checklist')
        download = self.client.get(arquivo_url, {'download': '1'})
        self.assertIn('attachment', download['Content-Disposition'])
        self.assertEqual(b''.join(download.streaming_content), b'%PDF-1.4 checklist')
        self.assertEqual(
            self.client.get(
                reverse('estoque:documentacao_cliente_detalhe', args=[cliente_fora.pk])
            ).status_code,
            404,
        )

    def test_relatorios_do_cliente_aparecem_na_central_e_na_resposta_da_tory(self):
        cliente = Cliente.objects.create(sigla='RPT', nome='Cliente com relatórios')
        Inventario.objects.create(
            cliente=cliente, loja='Loja R', base=self.base,
            data_inicio='2026-08-20', criado_por=self.user,
        )
        relatorio_obrigatorio = TipoRelatorioCliente.objects.create(
            nome='Relatório de divergências'
        )
        relatorio_opcional = TipoRelatorioCliente.objects.create(
            nome='Resumo fotográfico'
        )
        ClienteRelatorio.objects.create(
            cliente=cliente,
            tipo_relatorio=relatorio_obrigatorio,
            obrigatorio=True,
            observacao='Separar por loja.',
        )
        ClienteRelatorio.objects.create(
            cliente=cliente,
            tipo_relatorio=relatorio_opcional,
            obrigatorio=False,
            ordem=2,
        )

        self.client.force_login(self.user)
        detalhe = self.client.get(
            reverse('estoque:documentacao_cliente_detalhe', args=[cliente.pk])
        )
        self.assertContains(detalhe, 'RELATÓRIO DE DIVERGÊNCIAS')
        self.assertContains(detalhe, 'RESUMO FOTOGRÁFICO')
        self.assertContains(detalhe, 'SEPARAR POR LOJA.')

        resposta = AssistenteOperacionalService.responder(
            self.user, 'Tory, o que entregamos para o cliente RPT?'
        )
        self.assertIn('RELATÓRIO DE DIVERGÊNCIAS (obrigatório)', resposta['resposta'])
        self.assertIn('RESUMO FOTOGRÁFICO (opcional)', resposta['resposta'])

        busca = self.client.get(
            reverse('estoque:documentacao'), {'q': 'divergências'}
        )
        self.assertContains(busca, 'RPT - Checklist de entregáveis')

    def test_permissao_de_gestao_respeita_escopo_de_base(self):
        cliente_permitido = Cliente.objects.create(sigla='PERM', nome='Cliente permitido')
        cliente_fora = Cliente.objects.create(sigla='NEG', nome='Cliente negado')
        outra_empresa = Empresa.objects.create(nome='Empresa sem acesso')
        outra_base = Base.objects.create(nome='Base sem acesso', empresa=outra_empresa)
        Inventario.objects.create(
            cliente=cliente_permitido, loja='Loja 1', base=self.base,
            data_inicio='2026-08-20', criado_por=self.user,
        )
        Inventario.objects.create(
            cliente=cliente_fora, loja='Loja 2', base=outra_base,
            data_inicio='2026-08-20', criado_por=self.user,
        )
        permissao = Permission.objects.get(
            content_type__app_label='insumos',
            codename='gerenciar_documentacao',
        )
        self.user.user_permissions.add(permissao)
        self.client.force_login(self.user)

        permitido_url = reverse(
            'estoque:documentacao_cliente_detalhe', args=[cliente_permitido.pk]
        )
        resposta = self.client.post(
            permitido_url,
            {'arquivo': SimpleUploadedFile('permitido.pdf', b'%PDF-1.4 permitido')},
        )
        self.assertRedirects(resposta, permitido_url)
        self.assertTrue(
            ClienteChecklistDocumento.objects.filter(cliente=cliente_permitido).exists()
        )
        negado = self.client.post(
            reverse('estoque:documentacao_cliente_detalhe', args=[cliente_fora.pk]),
            {'arquivo': SimpleUploadedFile('negado.pdf', b'%PDF-1.4 negado')},
        )
        self.assertEqual(negado.status_code, 404)

    def test_admin_envia_e_substitui_o_arquivo_do_checklist(self):
        cliente = Cliente.objects.create(
            sigla='ADM', nome='Cliente administrável', status_relatorio='ATIVO'
        )
        admin = User.objects.create_user(username='admin-documentacao', password='segura-123')
        admin.perfil.role = 'admin'
        admin.perfil.save()
        self.client.force_login(admin)
        url = reverse('estoque:documentacao_cliente_detalhe', args=[cliente.pk])
        resposta = self.client.post(
            url,
            {'arquivo': SimpleUploadedFile(
                'orientacoes-finais.docx',
                _docx_minimo('Orientações finais exibidas sem download.'),
                content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            )},
        )
        self.assertRedirects(resposta, url)
        documento = ClienteChecklistDocumento.objects.get(cliente=cliente)
        self.assertEqual(documento.nome_original, 'orientacoes-finais.docx')
        self.assertEqual(documento.enviado_por, admin)
        cliente.refresh_from_db()
        self.assertEqual(cliente.status_relatorio, 'ATIVO')
        pagina = self.client.get(url)
        self.assertContains(pagina, 'Substituir checklist')
        self.assertContains(pagina, 'Visualizar sem baixar')
        self.assertContains(pagina, 'Orientações finais exibidas sem download.')
        self.assertContains(pagina, 'Prévia textual do Word')

        invalido = self.client.post(
            url,
            {'arquivo': SimpleUploadedFile('instrucoes.txt', b'arquivo invalido')},
        )
        self.assertEqual(invalido.status_code, 200)
        self.assertContains(invalido, 'Envie um arquivo PDF ou Word')

    def test_checklist_cujo_arquivo_sumiu_retorna_404_em_vez_de_500(self):
        cliente = Cliente.objects.create(sigla='AUS', nome='Arquivo ausente')
        Inventario.objects.create(
            cliente=cliente, loja='Loja 1', base=self.base,
            data_inicio='2026-08-20', criado_por=self.user,
        )
        documento = ClienteChecklistDocumento.objects.create(
            cliente=cliente,
            arquivo=SimpleUploadedFile('temporario.pdf', b'%PDF-1.4 temporario'),
            nome_original='temporario.pdf',
            enviado_por=self.user,
        )
        documento.arquivo.storage.delete(documento.arquivo.name)
        self.client.force_login(self.user)

        resposta = self.client.get(reverse(
            'estoque:documentacao_cliente_arquivo', args=[cliente.pk]
        ))

        self.assertEqual(resposta.status_code, 404)

    def test_admin_gerencia_videos_da_documentacao(self):
        admin = User.objects.create_user(username='admin-videos', password='segura-123')
        admin.perfil.role = 'admin'
        admin.perfil.save()
        self.client.force_login(admin)

        videos_url = reverse('estoque:documentacao_videos')
        resposta_video = self.client.post(videos_url, {
            'titulo': 'Configuração da Phaser 3020',
            'descricao': 'Passo a passo validado pelo suporte.',
            'url': 'https://example.com/videos/phaser-3020',
            'origem': 'INTERNO',
            'produto_codigo': 'IMP-BR-XR',
            'categoria': 'Impressoras',
            'tags': 'wifi, configuração',
            'duracao': '04:30',
            'publicado_em': '2026-08-25',
        })
        self.assertRedirects(resposta_video, videos_url)
        video = VideoDocumentacao.objects.get()
        self.assertEqual(video.criado_por, admin)
        pagina_videos = self.client.get(videos_url)
        self.assertContains(pagina_videos, video.titulo)
        self.assertContains(pagina_videos, 'https://example.com/videos/phaser-3020')
        self.assertContains(pagina_videos, 'rel="noopener noreferrer"')
        self.assertEqual(
            DocumentationService.listar(termo='wifi', tipo='VIDEO')[0]['objeto_id'],
            video.pk,
        )

        desativar_video = reverse('estoque:documentacao_video_desativar', args=[video.pk])
        self.assertRedirects(self.client.post(desativar_video), videos_url)
        video.refresh_from_db()
        self.assertFalse(video.ativo)

    def test_pagina_de_videos_e_exibida_em_espanhol(self):
        self.user.perfil.idioma = 'es'
        self.user.perfil.save(update_fields=['idioma'])
        self.client.force_login(self.user)

        pagina = self.client.get(reverse('estoque:documentacao_videos'))

        self.assertContains(pagina, 'Vídeos de apoyo')
        self.assertContains(pagina, 'resolver problemas comunes')
        self.assertContains(pagina, 'No hay vídeos publicados')

    def test_template_de_checklist_e_exibido_em_espanhol(self):
        self.user.perfil.role = 'admin'
        self.user.perfil.idioma = 'es'
        self.user.perfil.save(update_fields=['role', 'idioma'])
        self.client.force_login(self.user)

        pagina = self.client.get(reverse('estoque:checklist'))

        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, 'CHECK-LIST DE EQUIPOS E INSUMOS')
        self.assertContains(pagina, 'DECLARACIÓN DE RETIRO DE EQUIPOS')
        self.assertContains(pagina, 'Seleccione primero el inventario y la base.')
        self.assertFalse(DocumentationService.listar(tipo='VIDEO'))

    def test_video_do_youtube_e_incorporado_na_pagina(self):
        admin = User.objects.create_user(username='admin-youtube', password='segura-123')
        admin.perfil.role = 'admin'
        admin.perfil.save()
        self.client.force_login(admin)

        VideoDocumentacao.objects.create(
            titulo='Configuração em vídeo',
            url='https://youtu.be/dQw4w9WgXcQ?t=10',
            origem='FABRICANTE',
            criado_por=admin,
        )

        pagina = self.client.get(reverse('estoque:documentacao_videos'))
        self.assertContains(
            pagina,
            'src="https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"',
        )
        self.assertContains(pagina, 'allowfullscreen')
        self.assertNotContains(pagina, 'href="https://youtu.be/dQw4w9WgXcQ?t=10"')

    def test_url_nao_incorporavel_mantem_link_externo(self):
        admin = User.objects.create_user(username='admin-video-link', password='segura-123')
        admin.perfil.role = 'admin'
        admin.perfil.save()
        self.client.force_login(admin)

        VideoDocumentacao.objects.create(
            titulo='Vídeo interno',
            url='https://example.com/videos/configuracao',
            origem='INTERNO',
            criado_por=admin,
        )

        pagina = self.client.get(reverse('estoque:documentacao_videos'))
        self.assertContains(pagina, 'href="https://example.com/videos/configuracao"')
        self.assertNotContains(pagina, 'youtube-nocookie.com/embed/')

    def test_admin_envia_abre_e_desativa_relatorio_de_resolucao(self):
        admin = User.objects.create_user(
            username='admin-resolucoes',
            password='segura-123',
        )
        admin.perfil.role = 'admin'
        admin.perfil.save()
        self.client.force_login(admin)
        url = reverse('estoque:documentacao_resolucao')
        conteudo_pdf = b'%PDF-1.4 relatorio de teste'

        resposta = self.client.post(url, {
            'titulo': 'M52 - Solução de comunicação',
            'fabricante': 'MobyData',
            'modelo': 'M52',
            'categoria': 'Coletores',
            'idioma': 'es',
            'resumo': 'Passo a passo validado pelo suporte.',
            'tags': 'wi-fi, servidor',
            'arquivo': SimpleUploadedFile(
                'resolucao-m52.pdf',
                conteudo_pdf,
                content_type='application/pdf',
            ),
        })
        self.assertRedirects(resposta, url)
        documento = ResolucaoDocumento.objects.get()
        self.assertEqual(documento.nome_original, 'resolucao-m52.pdf')
        self.assertEqual(documento.criado_por, admin)
        self.assertEqual(documento.idioma, 'es')

        pagina = self.client.get(url, {'q': 'Solução de comunicação'})
        self.assertContains(pagina, documento.titulo)
        self.assertContains(pagina, 'Desativar')
        arquivo_url = reverse(
            'estoque:documentacao_resolucao_arquivo',
            args=[documento.pk],
        )
        self.assertContains(pagina, arquivo_url)
        arquivo = self.client.get(arquivo_url)
        self.assertEqual(arquivo.status_code, 200)
        self.assertEqual(arquivo['X-Frame-Options'], 'SAMEORIGIN')
        self.assertIn('inline', arquivo['Content-Disposition'])
        self.assertEqual(b''.join(arquivo.streaming_content), conteudo_pdf)

        desativar_url = reverse(
            'estoque:documentacao_resolucao_desativar',
            args=[documento.pk],
        )
        self.assertRedirects(self.client.post(desativar_url), url)
        documento.refresh_from_db()
        self.assertFalse(documento.ativo)
        self.assertEqual(self.client.get(arquivo_url).status_code, 404)

    def test_operador_nao_pode_enviar_relatorio_de_resolucao(self):
        self.client.force_login(self.user)
        url = reverse('estoque:documentacao_resolucao')
        pagina = self.client.get(url)
        self.assertNotContains(pagina, 'Enviar relatório de resolução')
        resposta = self.client.post(url, {
            'titulo': 'Envio negado',
            'fabricante': 'Teste',
            'modelo': 'Teste',
            'categoria': 'Coletores',
            'arquivo': SimpleUploadedFile(
                'negado.pdf',
                b'%PDF-1.4 negado',
                content_type='application/pdf',
            ),
        })
        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(ResolucaoDocumento.objects.exists())

    def test_resolucao_em_espanhol_exibe_interface_e_idioma_traduzidos(self):
        self.user.perfil.idioma = 'es'
        self.user.perfil.save(update_fields=['idioma'])
        ResolucaoDocumento.objects.create(
            titulo='Solución de impresión', fabricante='Xerox', modelo='3020',
            categoria='Impresoras', idioma='es', arquivo='documento.pdf',
            nome_original='solucion.pdf', criado_por=self.user,
        )
        self.client.force_login(self.user)

        pagina = self.client.get(
            reverse('estoque:documentacao_resolucao'), {'idioma': 'es'}
        )

        self.assertContains(pagina, 'Resolución de problemas')
        self.assertContains(pagina, 'SOLUCIÓN DE IMPRESIÓN')
        self.assertContains(pagina, 'Español')


class ToryDocumentationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='usuario-tory-documentacao', password='segura-123')

    def test_tory_distingue_procedimento_interno_de_manual_oficial(self):
        resolucao = AssistenteOperacionalService.responder(
            self.user, 'Tory, a Xerox 3020 está com código 43 no USB.'
        )
        self.assertEqual(resolucao['contexto']['tipo_documento'], 'RESOLUCAO')
        self.assertIn('procedimento interno', resolucao['resposta'].lower())
        self.assertTrue(any(acao['label'] == 'Abrir procedimento' for acao in resolucao['acoes']))

        manual = AssistenteOperacionalService.responder(
            self.user, 'Tory, qual é o manual da Xerox 3020?'
        )
        self.assertEqual(manual['contexto']['tipo_documento'], 'MANUAL_OFICIAL')
        self.assertIn('manual oficial', manual['resposta'].lower())

    def test_pergunta_operacional_nao_e_interceptada_pela_documentacao(self):
        self.assertIsNone(
            DocumentationService.tentar_responder('qual o status do equipamento patrimônio 123?')
        )
