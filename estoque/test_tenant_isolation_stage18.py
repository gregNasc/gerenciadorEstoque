from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from auditorias.models import CampanhaAuditoria
from compras.models import Aquisicao
from estoque.models import (
    Base,
    CapacidadeRelacionamentoEmpresa,
    Comunicado,
    ComunicadoArquivo,
    Empresa,
    Equipamento,
    Mensagem,
    MensagemArquivo,
    MensagemDestino,
    Produto,
    RelacionamentoEmpresa,
)
from insumos.models import Cliente, FornecedorInsumo, Inventario
from ordens_servico.models import OrdemServico, OrdemServicoAnexo


class Stage18TenantIsolationTests(TestCase):
    def setUp(self):
        self.tempdir = TemporaryDirectory()
        self.storage_settings = override_settings(MEDIA_ROOT=Path(self.tempdir.name))
        self.storage_settings.enable()

        self.empresa_a = Empresa.objects.create(nome='Empresa Stage18 A')
        self.empresa_b = Empresa.objects.create(nome='Empresa Stage18 B')
        from estoque.test_documentacao import _habilitar_documentacao
        _habilitar_documentacao(self.empresa_a, legado=False)
        _habilitar_documentacao(self.empresa_b, legado=False)
        self.base_a = Base.objects.create(nome='Base Stage18 A', empresa=self.empresa_a)
        self.base_b = Base.objects.create(nome='Base Stage18 B', empresa=self.empresa_b)
        self.admin_a = self._admin('admin-stage18-a', self.empresa_a)
        self.admin_b = self._admin('admin-stage18-b', self.empresa_b)
        self.superuser = User.objects.create_superuser(
            'super-stage18', password='teste-stage18'
        )
        self.produto = Produto.objects.create(
            codigo='STAGE18-PRODUTO',
            descricao='Produto Stage18',
            categoria='Equipamentos Stage18',
        )

    def tearDown(self):
        self.storage_settings.disable()
        self.tempdir.cleanup()

    @staticmethod
    def _admin(username, empresa):
        user = User.objects.create_user(username, password='teste-stage18')
        user.perfil.role = user.perfil.Role.ADMIN
        user.perfil.empresa = empresa
        user.perfil.save()
        return user

    @staticmethod
    def _arquivo(nome='arquivo.txt', conteudo=b'conteudo-stage18'):
        return SimpleUploadedFile(nome, conteudo, content_type='text/plain')

    def test_auditoria_exige_tenant_e_capability_exata(self):
        campanha = CampanhaAuditoria.objects.create(
            empresa=self.empresa_b,
            nome='Auditoria privada B',
            criado_por=self.admin_b,
        )
        self.client.force_login(self.admin_a)
        lista = self.client.get(reverse('auditorias:campanha_lista'))
        self.assertNotContains(lista, campanha.nome)
        self.assertEqual(
            self.client.get(
                reverse('auditorias:campanha_detalhe', args=[campanha.pk])
            ).status_code,
            404,
        )

        relacionamento = RelacionamentoEmpresa.objects.create(
            empresa_origem=self.empresa_a,
            empresa_destino=self.empresa_b,
            criado_por=self.superuser,
        )
        CapacidadeRelacionamentoEmpresa.objects.create(
            relacionamento=relacionamento,
            recurso=CapacidadeRelacionamentoEmpresa.Recurso.AUDITORIAS,
            acao=CapacidadeRelacionamentoEmpresa.Acao.VISUALIZAR,
            criado_por=self.superuser,
        )
        self.admin_a.perfil.empresas_acesso_adicional.add(self.empresa_b)
        self.assertEqual(
            self.client.get(
                reverse('auditorias:campanha_detalhe', args=[campanha.pk])
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                reverse('auditorias:campanha_editar', args=[campanha.pk])
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse('auditorias:relatorio_campanha', args=[campanha.pk, 'xlsx'])
            ).status_code,
            404,
        )

    def test_foto_de_equipamento_nao_e_publica_nem_cross_tenant(self):
        equipamento = Equipamento.objects.create(
            produto=self.produto,
            numero_serie='SERIE-STAGE18',
            patrimonio='PAT-STAGE18',
            codigo='EQ-STAGE18',
            regional=self.base_a,
            foto=self._arquivo('foto-stage18.jpg', b'foto-stage18'),
        )
        url = reverse(
            'estoque:equipamento_arquivo', args=[equipamento.pk, 'foto']
        )
        self.client.force_login(self.admin_b)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.admin_a)
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta['Cache-Control'], 'private, no-store')
        self.client.logout()
        self.assertEqual(self.client.get(f'/media/{equipamento.foto.name}').status_code, 404)

    def test_anexo_de_mensagem_exige_destinatario(self):
        mensagem = Mensagem.objects.create(
            titulo='Mensagem privada A',
            conteudo='Conteúdo',
            enviado_por=self.admin_a,
        )
        MensagemDestino.objects.create(mensagem=mensagem, usuario=self.admin_a)
        arquivo = MensagemArquivo.objects.create(
            mensagem=mensagem,
            arquivo=self._arquivo(),
            nome_original='arquivo.txt',
        )
        url = reverse('estoque:baixar_arquivo_mensagem', args=[arquivo.pk])
        self.client.force_login(self.admin_b)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.admin_a)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_anexo_de_comunicado_todos_continua_restrito_a_empresa(self):
        comunicado = Comunicado.objects.create(
            titulo='Comunicado A',
            mensagem='Somente A',
            tipo='INFO',
            criado_por=self.admin_a,
            empresa=self.empresa_a,
            enviar_para_todos=True,
        )
        comunicado.usuarios.add(self.admin_a)
        arquivo = ComunicadoArquivo.objects.create(
            comunicado=comunicado,
            arquivo=self._arquivo('comunicado.txt'),
        )
        url = reverse('estoque:baixar_arquivo_comunicado', args=[arquivo.pk])
        self.client.force_login(self.admin_b)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.admin_a)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_documentacao_de_cliente_e_filtrada_por_inventario_do_tenant(self):
        cliente_a = Cliente.objects.create(sigla='S18A', nome='Cliente Stage18 A')
        cliente_b = Cliente.objects.create(sigla='S18B', nome='Cliente Stage18 B')
        Inventario.objects.create(
            cliente=cliente_a,
            loja='001',
            base=self.base_a,
            data_inicio=date.today(),
            criado_por=self.admin_a,
        )
        Inventario.objects.create(
            cliente=cliente_b,
            loja='002',
            base=self.base_b,
            data_inicio=date.today(),
            criado_por=self.admin_b,
        )
        self.client.force_login(self.admin_a)
        pagina = self.client.get(reverse('estoque:documentacao_clientes'))
        self.assertContains(pagina, cliente_a.nome)
        self.assertNotContains(pagina, cliente_b.nome)
        self.assertEqual(
            self.client.get(
                reverse('estoque:documentacao_cliente_detalhe', args=[cliente_b.pk])
            ).status_code,
            404,
        )

    def test_documentacao_criada_por_admin_pertence_ao_tenant(self):
        self.client.force_login(self.admin_a)
        resposta = self.client.post(reverse('estoque:documentacao_resolucao'), {
            'titulo': 'Procedimento privado A',
            'fabricante': 'Fabricante A',
            'modelo': 'Modelo A',
            'categoria': 'Categoria A',
            'idioma': 'pt-br',
            'arquivo': self._arquivo('procedimento-a.pdf', b'%PDF-stage18'),
        })
        self.assertEqual(resposta.status_code, 302)
        from estoque.models import ResolucaoDocumento
        documento = ResolucaoDocumento.objects.get(titulo='PROCEDIMENTO PRIVADO A')
        self.assertEqual(documento.empresa, self.empresa_a)
        url = reverse('estoque:documentacao_resolucao_arquivo', args=[documento.pk])
        self.client.force_login(self.admin_b)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.superuser)
        pagina = self.client.get(reverse('estoque:documentacao_resolucao'))
        self.assertContains(pagina, 'Relatório em PDF')

    def test_anexo_de_os_exige_escopo_de_exportacao_da_empresa(self):
        ordem = OrdemServico.objects.create(
            numero='OS-STAGE18-B',
            ano=2026,
            tipo=OrdemServico.Tipo.OUTRO,
            empresa=self.empresa_b,
            base_responsavel=self.base_b,
            solicitante=self.admin_b,
            motivo='Teste de arquivo privado',
        )
        anexo = OrdemServicoAnexo.objects.create(
            ordem=ordem,
            arquivo=self._arquivo('os-stage18.txt'),
            nome_original='os-stage18.txt',
            hash_arquivo='0' * 64,
            enviado_por=self.admin_b,
        )
        url = reverse('ordens_servico:baixar_anexo', args=[anexo.pk])
        self.client.force_login(self.admin_a)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.admin_b)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_documento_de_compra_cross_tenant_retorna_404(self):
        fornecedor = FornecedorInsumo.objects.create(
            nome='Fornecedor Stage18', documento='12345678000199'
        )
        aquisicao = Aquisicao.objects.create(
            empresa=self.empresa_b,
            fornecedor=fornecedor,
            cadastrado_por=self.admin_b,
            arquivo_danfe_pdf=self._arquivo('danfe-stage18.pdf', b'%PDF-stage18'),
        )
        url = reverse('compras:aquisicao_documento', args=[aquisicao.pk, 'danfe'])
        self.client.force_login(self.admin_a)
        self.assertEqual(self.client.get(url).status_code, 404)
