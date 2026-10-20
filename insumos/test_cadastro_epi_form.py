from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from estoque.models import Base, Empresa, Perfil
from insumos.models import CategoriaInsumo, Insumo, LoteEpi


class CadastroEpiFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = Empresa.objects.create(nome='Empresa Cadastro EPI')
        cls.base = Base.objects.create(nome='Base Cadastro EPI', empresa=cls.empresa)
        cls.outra_empresa = Empresa.objects.create(nome='Outra Empresa Cadastro EPI')
        cls.outra_base = Base.objects.create(
            nome='Base Oculta Cadastro EPI', empresa=cls.outra_empresa,
        )
        cls.admin = User.objects.create_user('admin.cadastro.epi', password='senha')
        cls.admin.perfil.empresa = cls.empresa
        cls.admin.perfil.role = Perfil.Role.ADMIN
        cls.admin.perfil.save(update_fields=['empresa', 'role'])
        cls.categoria = CategoriaInsumo.objects.create(nome='EPI Cadastro')

    def _dados_basicos(self, descricao):
        return {
            'descricao': descricao,
            'termo_pesquisa_online': '',
            'categoria': self.categoria.pk,
            'unidade_medida': 'PAR',
            'natureza': Insumo.Natureza.EPI,
            'forma_controle': Insumo.FormaControle.LOTE,
            'base_lote': self.base.pk,
            'numero_ca': f'CA-{descricao}',
            'tamanho_variante': 'ÚNICO',
            'estoque_minimo': '2.00',
            'estoque_maximo': '',
            'ativo': 'on',
        }

    def test_epi_pode_ser_cadastrado_sem_lote_e_sem_validades(self):
        self.client.force_login(self.admin)

        resposta = self.client.post(
            reverse('insumos:criar_item_insumo'),
            self._dados_basicos('EPI sem dados opcionais'),
        )

        self.assertEqual(
            resposta.status_code,
            302,
            getattr(resposta.context and resposta.context.get('form'), 'errors', ''),
        )
        insumo = Insumo.objects.get(descricao__iexact='EPI sem dados opcionais')
        self.assertRedirects(
            resposta,
            reverse('insumos:editar_insumos', args=[insumo.pk]),
        )
        self.assertEqual(insumo.dados_epi.fabricante_importador, '')
        self.assertTrue(insumo.dados_epi.certificados.exists())
        self.assertTrue(insumo.dados_epi.variantes.exists())
        lote = insumo.dados_epi.lotes.get()
        self.assertEqual(lote.base, self.base)
        self.assertEqual(lote.codigo_lote, '')

    def test_cadastro_de_bota_aceita_ca_lote_validade_e_tamanho(self):
        self.client.force_login(self.admin)
        dados = self._dados_basicos('Botas')
        dados.update({
            'fabricante_importador': 'Fabricante da Bota',
            'numero_ca': ' ca-bota-01 ',
            'validade_ca': '2029-12-31',
            'tamanho_variante': '',
            'tamanho_bota': '39',
            'base_lote': self.base.pk,
            'codigo_lote': ' lote-bota-01 ',
            'fabricado_em': '2026-01-10',
            'validade_fisica': '2028-01-10',
            'observacao_epi': 'Uso operacional',
        })

        resposta = self.client.post(reverse('insumos:criar_item_insumo'), dados)

        self.assertEqual(
            resposta.status_code,
            302,
            getattr(resposta.context and resposta.context.get('form'), 'errors', ''),
        )
        produto = Insumo.objects.get(categoria=self.categoria).dados_epi
        self.assertEqual(produto.insumo.descricao, 'Botas')
        self.assertEqual(produto.certificados.get().numero_ca, 'CA-BOTA-01')
        self.assertEqual(produto.variantes.get().tamanho, '39')
        lote = produto.lotes.get()
        self.assertEqual(lote.codigo_lote, 'LOTE-BOTA-01')
        self.assertEqual(lote.base, self.base)

    def test_tamanho_pode_ser_informado_sem_numero_de_lote(self):
        self.client.force_login(self.admin)
        dados = self._dados_basicos('Bota sem lote')
        dados['tamanho_variante'] = ''
        dados['tamanho_bota'] = '42'

        resposta = self.client.post(reverse('insumos:criar_item_insumo'), dados)

        self.assertEqual(
            resposta.status_code,
            302,
            getattr(resposta.context and resposta.context.get('form'), 'errors', ''),
        )
        produto = Insumo.objects.get(descricao__iexact='Bota sem lote').dados_epi
        self.assertEqual(produto.variantes.get().tamanho, '42')
        lote = LoteEpi.objects.get(produto_epi=produto)
        self.assertEqual(lote.codigo_lote, '')
        self.assertEqual(lote.base, self.base)

    def test_base_e_obrigatoria_para_epi(self):
        self.client.force_login(self.admin)
        dados = self._dados_basicos('EPI sem Base')
        dados['base_lote'] = ''

        resposta = self.client.post(reverse('insumos:criar_item_insumo'), dados)

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Selecione a Base em que o EPI será cadastrado.')
        self.assertFalse(Insumo.objects.filter(descricao__iexact='EPI sem Base').exists())

    def test_ca_e_tamanho_sao_obrigatorios_para_epi(self):
        self.client.force_login(self.admin)
        dados = self._dados_basicos('EPI sem CA e tamanho')
        dados['numero_ca'] = ''
        dados['tamanho_variante'] = ''

        resposta = self.client.post(reverse('insumos:criar_item_insumo'), dados)

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Informe o CA do EPI.')
        self.assertContains(resposta, 'Informe o tamanho ou a variante do EPI.')
        self.assertFalse(
            Insumo.objects.filter(descricao__iexact='EPI sem CA e tamanho').exists()
        )

    def test_edicao_nao_exibe_lote_de_outro_tenant(self):
        self.client.force_login(self.admin)
        dados = self._dados_basicos('EPI isolado por Base')
        resposta = self.client.post(reverse('insumos:criar_item_insumo'), dados)
        self.assertEqual(resposta.status_code, 302)
        insumo = Insumo.objects.get(descricao__iexact='EPI isolado por Base')
        produto = insumo.dados_epi
        LoteEpi.objects.create(
            base=self.outra_base,
            produto_epi=produto,
            variante=produto.variantes.get(),
            certificado=produto.certificados.get(),
            codigo_lote='LOTE-OCULTO-OUTRO-TENANT',
        )

        pagina = self.client.get(reverse('insumos:editar_insumos', args=[insumo.pk]))

        self.assertEqual(pagina.status_code, 200)
        self.assertNotContains(pagina, 'LOTE-OCULTO-OUTRO-TENANT')
        self.assertNotContains(pagina, self.outra_base.nome)
