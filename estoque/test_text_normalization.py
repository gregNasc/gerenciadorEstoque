from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.test import TestCase

from estoque.models import Empresa, GrupoRegional, Perfil
from insumos.models import FornecedorInsumo


class NormalizacaoCaixaAltaTests(TestCase):
    def test_salva_campos_de_negocio_em_caixa_alta(self):
        empresa = Empresa.objects.create(nome='Inventário São Paulo')
        fornecedor = FornecedorInsumo.objects.create(
            nome='Fornecedor Central',
            documento='ab-123',
            contato='Maria da Silva',
            email='Contato@Fornecedor.com',
            site='https://Fornecedor.com/Catalogo',
            observacao='entrega somente pela manhã',
        )

        self.assertEqual(empresa.nome, 'INVENTÁRIO SÃO PAULO')
        self.assertEqual(fornecedor.nome, 'FORNECEDOR CENTRAL')
        self.assertEqual(fornecedor.documento, 'AB-123')
        self.assertEqual(fornecedor.contato, 'MARIA DA SILVA')
        self.assertEqual(fornecedor.observacao, 'ENTREGA SOMENTE PELA MANHÃ')
        self.assertEqual(fornecedor.email, 'Contato@Fornecedor.com')
        self.assertEqual(fornecedor.site, 'https://Fornecedor.com/Catalogo')

        usuario = User.objects.create_user(
            username='usuario.case.sensitive',
            email='Pessoa@Empresa.com',
            password='SenhaCaseSensitive123!',
            first_name='João',
            last_name='da Silva',
        )
        self.assertEqual(usuario.username, 'usuario.case.sensitive')
        self.assertEqual(usuario.email, 'Pessoa@empresa.com')
        self.assertTrue(usuario.check_password('SenhaCaseSensitive123!'))
        self.assertEqual(usuario.first_name, 'JOÃO')
        self.assertEqual(usuario.last_name, 'DA SILVA')

    def test_preserva_valores_internos_de_choices(self):
        self.assertEqual(Perfil.Role.ADMIN, 'admin')

    def test_impede_duplicidade_de_campo_unico_independente_da_caixa(self):
        GrupoRegional.objects.create(nome='Regional Sudeste')

        duplicado = GrupoRegional(nome='regional sudeste')
        with self.assertRaises(ValidationError):
            duplicado.full_clean()
        with self.assertRaises(ValidationError):
            duplicado.save()

        User.objects.create_user('usuario.unico', password='SenhaForte123!')
        with self.assertRaises(ValidationError):
            User.objects.create_user('USUARIO.UNICO', password='OutraSenha123!')
