import tempfile

from django.contrib.auth.models import User
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from estoque.models import (
    Base,
    Empresa,
    ResolucaoDocumento,
    SecaoDocumentacaoEmpresa,
)
from estoque.services.documentation_service import DocumentationService


class DocumentationSectionsIsolationTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.file_field = ResolucaoDocumento._meta.get_field('arquivo')
        self.original_storage = self.file_field.storage
        self.file_field.storage = FileSystemStorage(location=self.temp_dir.name)

        self.company_a = Empresa.objects.create(nome='Tenant documental A')
        self.company_b = Empresa.objects.create(nome='Tenant documental B')
        self.company_empty = Empresa.objects.create(nome='Tenant sem documentação')
        self.user_a = self._user_for(self.company_a, 'docs-a')
        self.user_b = self._user_for(self.company_b, 'docs-b')
        self.user_empty = self._user_for(self.company_empty, 'docs-empty')

        for company, legacy in ((self.company_a, False), (self.company_b, True)):
            for code in (
                SecaoDocumentacaoEmpresa.Codigo.BIBLIOTECA,
                SecaoDocumentacaoEmpresa.Codigo.MANUAIS,
                SecaoDocumentacaoEmpresa.Codigo.RESOLUCOES,
            ):
                SecaoDocumentacaoEmpresa.objects.create(
                    empresa=company,
                    codigo=code,
                    habilitado=True,
                    nome_exibicao=(
                        'Manual Operacional'
                        if company == self.company_a
                        and code == SecaoDocumentacaoEmpresa.Codigo.MANUAIS
                        else ''
                    ),
                    permite_conteudo_global_legado=legacy,
                )

    def tearDown(self):
        self.file_field.storage = self.original_storage
        self.temp_dir.cleanup()
        super().tearDown()

    @staticmethod
    def _user_for(company, username):
        user = User.objects.create_user(username=username, password='teste-123')
        base = Base.objects.create(nome=f'Base {username}', empresa=company)
        user.perfil.empresa = company
        user.perfil.role = 'operador'
        user.perfil.save(update_fields=['empresa', 'role'])
        user.perfil.regionais.add(base)
        return user

    def test_tenant_sem_configuracao_nao_exibe_menu_nem_acessa_secao(self):
        self.client.force_login(self.user_empty)
        dashboard = self.client.get(reverse('estoque:index'), follow=True)
        self.assertNotContains(dashboard, 'documentacaoDropdown')
        self.assertEqual(
            self.client.get(reverse('estoque:documentacao')).status_code,
            403,
        )

    def test_menu_usa_nome_customizado_e_oculta_secoes_desabilitadas(self):
        self.client.force_login(self.user_a)
        page = self.client.get(reverse('estoque:documentacao'))
        self.assertContains(page, 'Manual Operacional')
        self.assertNotContains(page, reverse('estoque:drivers_impressoras'))
        self.assertNotContains(page, reverse('estoque:documentacao_videos'))
        self.assertEqual(
            self.client.get(reverse('estoque:drivers_impressoras')).status_code,
            403,
        )

    def test_acervo_legado_exige_liberacao_explicita_e_download_autenticado(self):
        legacy = next(
            item for item in DocumentationService._dados_catalogo()
            if DocumentationService._preparar_item(item)['arquivo_disponivel']
        )
        url = reverse(
            'estoque:documentacao_legado_arquivo', args=[legacy['id']]
        )

        self.client.force_login(self.user_a)
        self.assertFalse(DocumentationService._legacy_catalog(self.user_a))
        self.assertEqual(self.client.get(url).status_code, 404)

        self.client.force_login(self.user_b)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')

    def test_documento_e_download_de_outro_tenant_sao_negados(self):
        foreign_document = ResolucaoDocumento.objects.create(
            empresa=self.company_b,
            titulo='Documento exclusivo B',
            fabricante='Fornecedor B',
            modelo='Modelo B',
            categoria='Categoria B',
            arquivo=SimpleUploadedFile(
                'exclusivo-b.pdf', b'%PDF-1.4 tenant-b',
                content_type='application/pdf',
            ),
            nome_original='exclusivo-b.pdf',
            criado_por=self.user_b,
        )
        self.client.force_login(self.user_a)
        listing = self.client.get(reverse('estoque:documentacao_resolucao'))
        self.assertNotContains(listing, 'Documento exclusivo B')
        direct = self.client.get(reverse(
            'estoque:documentacao_resolucao_arquivo',
            args=[foreign_document.pk],
        ))
        self.assertEqual(direct.status_code, 404)

    def test_secao_desabilitada_bloqueia_post_e_download_sem_apagar_documentos(self):
        self.user_a.perfil.role = 'admin'
        self.user_a.perfil.save(update_fields=['role'])
        document = ResolucaoDocumento.objects.create(
            empresa=self.company_a, titulo='Documento preservado',
            arquivo='preservado.pdf', criado_por=self.user_a,
        )
        SecaoDocumentacaoEmpresa.objects.filter(
            empresa=self.company_a, codigo='resolucoes',
        ).update(habilitado=False)
        self.client.force_login(self.user_a)
        self.assertEqual(self.client.post(reverse('estoque:documentacao_resolucao'), {}).status_code, 403)
        self.assertEqual(self.client.get(reverse('estoque:documentacao_resolucao_arquivo', args=[document.pk])).status_code, 403)
        self.assertTrue(ResolucaoDocumento.objects.filter(pk=document.pk).exists())

    def test_urls_estaticas_legadas_nao_contornam_download_protegido(self):
        for path in (
            '/static/manuais/xerox-phaser-3020-guia-usuario-pt-br.pdf',
            '/static/documentacao/resolucao/resolucao_xerox_phaser_3020.pdf',
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)
