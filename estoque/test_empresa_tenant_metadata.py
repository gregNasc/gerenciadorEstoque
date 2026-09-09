from django.test import TestCase

from estoque.models import Empresa


class EmpresaTenantMetadataTests(TestCase):
    def test_nova_empresa_recebe_metadados_compativeis(self):
        empresa = Empresa.objects.create(nome='Empresa de Teste')

        self.assertTrue(empresa.ativa)
        self.assertIsNone(empresa.slug)
        self.assertIsNotNone(empresa.criado_em)
        self.assertIsNotNone(empresa.atualizado_em)

    def test_slug_permanece_opcional_durante_transicao(self):
        empresa = Empresa.objects.create(nome='Tenant ainda sem slug', slug='')

        empresa.refresh_from_db()
        self.assertEqual(empresa.slug, '')

    def test_slug_pode_ser_definido_sem_alterar_nome_exibido(self):
        empresa = Empresa.objects.create(
            nome='Inventory Exemplo',
            slug='inventory-exemplo',
        )

        self.assertEqual(empresa.slug, 'inventory-exemplo')
        self.assertEqual(empresa.nome, 'INVENTORY EXEMPLO')
        self.assertEqual(str(empresa), empresa.nome)
