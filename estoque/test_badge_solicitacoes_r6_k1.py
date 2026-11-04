from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.test import RequestFactory, TestCase
from django.urls import reverse

from estoque.context_processors import notificacoes_context
from estoque.models import Base, Empresa, Perfil, Solicitacao
from insumos.constants import GruposInsumos
from insumos.models import SolicitacaoInsumo
from insumos.services.solicitacao_service import SolicitacaoConsultaService


class BadgeSolicitacoesR6K1Tests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.empresa_a = Empresa.objects.create(nome='Empresa K1 A')
        self.empresa_b = Empresa.objects.create(nome='Empresa K1 B')
        self.base_a = Base.objects.create(nome='BASE K1 A', empresa=self.empresa_a)
        self.base_a_2 = Base.objects.create(nome='BASE K1 A 2', empresa=self.empresa_a)
        self.base_b = Base.objects.create(nome='BASE K1 B', empresa=self.empresa_b)
        self.admin_a = self._usuario('admin_k1_a', self.empresa_a, Perfil.Role.ADMIN)
        self.admin_b = self._usuario('admin_k1_b', self.empresa_b, Perfil.Role.ADMIN)
        self.gestor_a = self._usuario('gestor_k1_a', self.empresa_a, Perfil.Role.GESTOR)
        self.compras_a = self._usuario('compras_k1_a', self.empresa_a, Perfil.Role.GESTOR)
        self.gestor_a.perfil.regionais.add(self.base_a)
        self.compras_a.perfil.regionais.add(self.base_a)
        grupo, _ = Group.objects.get_or_create(name=GruposInsumos.COMPRAS)
        self.compras_a.groups.add(grupo)

    @staticmethod
    def _usuario(username, empresa, role):
        usuario = User.objects.create_user(username, password='teste')
        Perfil.objects.update_or_create(
            user=usuario,
            defaults={'empresa': empresa, 'role': role},
        )
        usuario.refresh_from_db()
        return usuario

    @staticmethod
    def _solicitacao(base, solicitante, protocolo, status='PENDENTE'):
        return SolicitacaoInsumo.objects.create(
            protocolo=protocolo,
            base=base,
            solicitante=solicitante,
            status=status,
            prioridade='MEDIA',
        )

    def test_contador_usa_r6_apenas_no_tenant_e_ignora_legado_e_encerradas(self):
        self._solicitacao(self.base_a, self.gestor_a, 'K1-A-PENDENTE')
        self._solicitacao(
            self.base_a, self.gestor_a, 'K1-A-ANALISE', status='EM_ANALISE',
        )
        self._solicitacao(
            self.base_a, self.gestor_a, 'K1-A-FINAL', status='FINALIZADA',
        )
        self._solicitacao(self.base_b, self.admin_b, 'K1-B-PENDENTE')
        Solicitacao.objects.create(
            motivo='Pedido legado não deve entrar no badge R6.',
            regional_solicitante=self.base_a,
            criado_por=self.gestor_a,
        )

        self.assertEqual(
            SolicitacaoConsultaService.contar_pendencias_acionaveis(self.admin_a),
            2,
        )
        self.assertEqual(
            SolicitacaoConsultaService.contar_pendencias_acionaveis(self.admin_b),
            1,
        )

    def test_compras_respeita_bases_e_gestor_sem_competencia_nao_recebe_badge(self):
        self._solicitacao(self.base_a, self.gestor_a, 'K1-BASE-PERMITIDA')
        self._solicitacao(self.base_a_2, self.admin_a, 'K1-BASE-FORA-ESCOPO')

        self.assertEqual(
            SolicitacaoConsultaService.contar_pendencias_acionaveis(self.compras_a),
            1,
        )
        self.assertEqual(
            SolicitacaoConsultaService.contar_pendencias_acionaveis(self.gestor_a),
            0,
        )

    @patch('estoque.context_processors.TenantFeatureService.user_has_feature', return_value=True)
    @patch('estoque.services.comunicado_service.ComunicadoService.excluir_expirados')
    @patch('estoque.services.comunicado_service.ComunicadoService.notificar_manutencoes_previstas')
    def test_context_processor_nao_escreve_e_expoe_contador_canonico(
        self, notificar, excluir, _feature,
    ):
        self._solicitacao(self.base_a, self.gestor_a, 'K1-CONTEXTO')
        request = self.factory.get('/')
        request.user = self.admin_a
        request.tenant = self.empresa_a

        contexto = notificacoes_context(request)

        self.assertEqual(contexto['solicitacoes_pendentes'], 1)
        self.assertEqual(contexto['notificacoes_pendentes'], 0)
        notificar.assert_not_called()
        excluir.assert_not_called()

    @patch('estoque.context_processors.TenantFeatureService.user_has_feature', return_value=True)
    def test_badge_aparece_em_solicitacoes_e_nao_em_transferencias(
        self, _feature,
    ):
        self._solicitacao(self.base_a, self.gestor_a, 'K1-MENU')
        self.client.force_login(self.admin_a)

        resposta = self.client.get(reverse('insumos:lista_solicitacoes_insumo'))

        self.assertEqual(resposta.status_code, 200)
        html = resposta.content.decode()
        bloco_solicitacoes = html.split(
            '<!-- SOLICITAÇÕES -->', 1,
        )[1].split('<!-- TRANSFERÊNCIAS -->', 1)[0]
        bloco_transferencias = html.split('<!-- TRANSFERÊNCIAS -->', 1)[1]
        self.assertIn('id="dropdownSolicitacoes"', bloco_solicitacoes)
        self.assertEqual(bloco_solicitacoes.count('badge-notificacao'), 1)
        self.assertNotIn('badge-notificacao', bloco_transferencias)

    @patch('estoque.context_processors.TenantFeatureService.user_has_feature', return_value=False)
    def test_modulo_insumos_desabilitado_nao_consulta_nem_expoe_badge(
        self, _feature,
    ):
        self._solicitacao(self.base_a, self.gestor_a, 'K1-MODULO-OFF')
        request = self.factory.get('/')
        request.user = self.admin_a
        request.tenant = self.empresa_a

        with patch.object(
            SolicitacaoConsultaService,
            'contar_pendencias_acionaveis',
        ) as contar:
            contexto = notificacoes_context(request)

        self.assertEqual(contexto['solicitacoes_pendentes'], 0)
        contar.assert_not_called()
