from datetime import timedelta
from io import BytesIO

import openpyxl
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from estoque.models import Base, Empresa, Perfil
from insumos.models import (
    CategoriaInsumo,
    CertificadoEpi,
    Insumo,
    LoteEpi,
    ProdutoEpi,
    VarianteEpi,
)


class ExportacaoEpiR3GTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = Empresa.objects.create(nome='Empresa exportação EPI')
        cls.base = Base.objects.create(nome='Base exportação EPI', empresa=cls.empresa)
        cls.outra_empresa = Empresa.objects.create(nome='Outro tenant EPI')
        cls.outra_base = Base.objects.create(nome='Base proibida EPI', empresa=cls.outra_empresa)
        cls.admin = User.objects.create_user('admin.exportacao.epi', password='senha')
        cls.admin.perfil.empresa = cls.empresa
        cls.admin.perfil.role = Perfil.Role.ADMIN
        cls.admin.perfil.save(update_fields=['empresa', 'role'])
        categoria = CategoriaInsumo.objects.create(nome='EPI')
        cls.insumo = Insumo.objects.create(
            descricao='Botas exportação',
            categoria=categoria,
            unidade_medida='PAR',
            natureza=Insumo.Natureza.EPI,
        )
        produto = ProdutoEpi.objects.create(insumo=cls.insumo)
        variante = VarianteEpi.objects.create(
            produto_epi=produto,
            nome='Botas',
            tamanho='37',
        )
        hoje = timezone.localdate()
        vencido = CertificadoEpi.objects.create(
            produto_epi=produto,
            numero_ca='11111',
            validade_ca=hoje - timedelta(days=1),
            situacao_oficial='VENCIDO',
            snapshot_oficial={'natureza': 'Nacional'},
        )
        proximo = CertificadoEpi.objects.create(
            produto_epi=produto,
            numero_ca='22222',
            validade_ca=hoje + timedelta(days=90),
            situacao_oficial='VÁLIDO',
        )
        vigente = CertificadoEpi.objects.create(
            produto_epi=produto,
            numero_ca='33333',
            validade_ca=hoje + timedelta(days=400),
            situacao_oficial='VÁLIDO',
        )
        LoteEpi.objects.create(
            base=cls.base, produto_epi=produto, variante=variante,
            certificado=vencido, codigo_lote='VENCIDO-1', ativo=True,
        )
        LoteEpi.objects.create(
            base=cls.base, produto_epi=produto, variante=variante,
            certificado=proximo, codigo_lote='PROXIMO-1', ativo=False,
        )
        LoteEpi.objects.create(
            base=cls.base, produto_epi=produto, variante=variante,
            certificado=vigente, codigo_lote='VIGENTE-1', ativo=True,
        )

    def test_exporta_filtros_de_validade_e_atividade_sem_precos(self):
        self.client.force_login(self.admin)
        resposta = self.client.get(reverse('insumos:exportar_dados_epi'), {
            'base': self.base.pk,
            'insumo': self.insumo.pk,
            'validade': ['vencido', 'proximo'],
            'registro': ['ativo', 'inativo'],
        })

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            resposta['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        planilha = openpyxl.load_workbook(BytesIO(resposta.content)).active
        valores = [celula for linha in planilha.iter_rows(values_only=True) for celula in linha]
        self.assertIn('VENCIDO-1', valores)
        self.assertIn('PROXIMO-1', valores)
        self.assertNotIn('VIGENTE-1', valores)
        cabecalhos = [celula.value for celula in planilha[1]]
        self.assertNotIn('PREÇO', cabecalhos)
        self.assertNotIn('CUSTO', cabecalhos)
        self.assertNotIn('VALOR', cabecalhos)

    def test_rejeita_exportacao_de_base_de_outro_tenant(self):
        self.client.force_login(self.admin)
        resposta = self.client.get(reverse('insumos:exportar_dados_epi'), {
            'base': self.outra_base.pk,
            'insumo': self.insumo.pk,
        })
        self.assertEqual(resposta.status_code, 403)

