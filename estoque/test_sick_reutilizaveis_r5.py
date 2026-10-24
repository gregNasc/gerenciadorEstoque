from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from estoque.models import Base, Empresa, Perfil, Sick
from estoque.services.sick_service import SickService
from insumos.models import (
    AtivoInsumoIndividualizado,
    CategoriaInsumo,
    HistoricoInsumo,
    Insumo,
)
from ordens_servico.models import OrdemServicoLinha


class SickAtivoReutilizavelR5Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = Empresa.objects.create(nome='Tenant R5')
        cls.base = Base.objects.create(nome='Base R5', empresa=cls.empresa)
        cls.outra_empresa = Empresa.objects.create(nome='Outro Tenant R5')
        cls.outra_base = Base.objects.create(nome='Base Oculta R5', empresa=cls.outra_empresa)
        cls.gestor = cls._usuario('gestor.r5', cls.empresa, cls.base)
        cls.gestor_outro = cls._usuario('gestor.outro.r5', cls.outra_empresa, cls.outra_base)
        categoria = CategoriaInsumo.objects.create(nome='Operacional R5')
        cls.insumo = Insumo.objects.create(
            descricao='Balança R5',
            categoria=categoria,
            unidade_medida='UN',
            natureza=Insumo.Natureza.REUTILIZAVEL,
            forma_controle=Insumo.FormaControle.INDIVIDUALIZADO,
        )

    @classmethod
    def _usuario(cls, username, empresa, base):
        usuario = User.objects.create_user(username, password='senha')
        usuario.perfil.role = Perfil.Role.GESTOR
        usuario.perfil.empresa = empresa
        usuario.perfil.save(update_fields=['role', 'empresa'])
        usuario.perfil.regionais.add(base)
        return usuario

    def _ativo(self, patrimonio='BAL-R5-001'):
        return AtivoInsumoIndividualizado.objects.create(
            base=self.base,
            insumo=self.insumo,
            patrimonio=patrimonio,
        )

    def _abrir(self, ativo, usuario=None):
        return SickService.marcar_ativo_insumo_como_sick(
            ativo_insumo_id=ativo.pk,
            usuario=usuario or self.gestor,
            categoria='ELETRÔNICA',
            motivo='Não estabiliza a leitura',
            observacao='Falha confirmada durante a operação',
        )

    def test_abertura_muda_status_cria_historico_e_ordem(self):
        ativo = self._ativo()

        sick = self._abrir(ativo)

        ativo.refresh_from_db()
        self.assertEqual(ativo.status, AtivoInsumoIndividualizado.Status.SICK)
        self.assertTrue(ativo.ativo)
        self.assertIsNone(sick.equipamento_id)
        self.assertEqual(sick.ativo_insumo_id, ativo.pk)
        self.assertEqual(sick.base_alvo, self.base)
        self.assertTrue(
            HistoricoInsumo.objects.filter(tipo='SICK', dados__sick_id=sick.pk).exists()
        )
        linha = OrdemServicoLinha.objects.get(ordem__sick=sick)
        self.assertEqual(linha.insumo, self.insumo)
        self.assertEqual(linha.patrimonio, ativo.patrimonio)
        self.assertEqual(
            linha.dados_snapshot['tipo_item'],
            'ATIVO_INSUMO_INDIVIDUALIZADO',
        )

    def test_nao_abre_segundo_sick_ativo_para_mesma_unidade(self):
        ativo = self._ativo()
        self._abrir(ativo)

        with self.assertRaises(ValidationError):
            self._abrir(ativo)

    def test_sick_reutilizavel_respeita_escopo_do_tenant(self):
        sick = self._abrir(self._ativo())

        self.assertTrue(SickService.visiveis_para(self.gestor).filter(pk=sick.pk).exists())
        self.assertFalse(
            SickService.visiveis_para(self.gestor_outro).filter(pk=sick.pk).exists()
        )

    def test_tela_sick_renderiza_unidade_reutilizavel(self):
        sick = self._abrir(self._ativo())
        self.client.force_login(self.gestor)

        resposta = self.client.get(
            reverse('estoque:sick'),
            {'etapa': Sick.Etapa.IDENTIFICADO, 'sick': sick.pk},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'BAL-R5-001')
        self.assertContains(resposta, 'Unidade reutilizável individualizada')

    def test_gestor_abre_sick_pelo_endpoint_do_estoque(self):
        ativo = self._ativo()
        self.client.force_login(self.gestor)

        resposta = self.client.post(
            reverse('insumos:marcar_ativo_insumo_sick', args=[ativo.pk]),
            {
                'categoria': 'CALIBRAÇÃO',
                'motivo': 'Oscilação',
                'observacao': 'Teste de bancada reprovado',
            },
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(Sick.objects.filter(ativo_insumo=ativo, ativo=True).exists())

    def test_banco_exige_exatamente_um_alvo(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Sick.objects.create(
                    base_origem=self.base,
                    categoria='SEM ALVO',
                    motivo='Inválido',
                )
