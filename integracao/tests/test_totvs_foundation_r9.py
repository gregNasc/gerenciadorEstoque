from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from estoque.models import Empresa
from integracao.exceptions import (
    TotvsAmbiguousResultError,
    TotvsConfigurationError,
    TotvsRetryableError,
)
from integracao.models import (
    TotvsIntegrationConfig,
    TotvsOperation,
    TotvsOperationAttempt,
)
from integracao.totvs.contracts import TotvsAdapterResult
from integracao.totvs.operation_service import TotvsOperationService
from integracao.totvs.readiness import TotvsReadinessService
from integracao.totvs.registry import TotvsAdapterRegistry


class FakeTotvsAdapter:
    def __init__(self, error=None):
        self.error = error
        self.calls = 0

    def enviar(self, *, config, operacao):
        self.calls += 1
        if self.error:
            raise self.error
        return TotvsAdapterResult(
            referencia_remota='PEDIDO-123',
            status_remoto='INCLUIDO',
            confirmado=True,
            http_status=201,
            requisicao_sha256='a' * 64,
            resposta_sha256='b' * 64,
        )

    def reconciliar(self, *, config, operacao):
        return self.enviar(config=config, operacao=operacao)


class TotvsFoundationR9Tests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa R9', slug='empresa-r9')

    def tearDown(self):
        TotvsAdapterRegistry.unregister(TotvsIntegrationConfig.Produto.PROTHEUS)

    def _config(self, **overrides):
        values = {
            'empresa': self.empresa,
            'habilitada': True,
            'produto': TotvsIntegrationConfig.Produto.PROTHEUS,
            'versao': '12.1.x',
            'modulos': ['Compras'],
            'ambiente': TotvsIntegrationConfig.Ambiente.HOMOLOGACAO,
            'api_base_url': 'https://totvs-homolog.example.test/api',
        }
        values.update(overrides)
        return TotvsIntegrationConfig.objects.create(**values)

    def test_configuracao_incompleta_permanece_desabilitada(self):
        config = TotvsIntegrationConfig.objects.create(empresa=self.empresa)

        self.assertFalse(config.habilitada)
        self.assertEqual(config.produto, TotvsIntegrationConfig.Produto.NAO_DEFINIDO)

    def test_diagnostico_e_somente_leitura_e_pode_falhar_gate(self):
        TotvsIntegrationConfig.objects.create(empresa=self.empresa)
        output = StringIO()

        call_command('check_totvs_readiness', stdout=output)

        self.assertIn('bloqueada', output.getvalue())
        with self.assertRaises(CommandError):
            call_command('check_totvs_readiness', '--fail-on-blocker')

    def test_nao_habilita_sem_produto_versao_modulo_e_api(self):
        with self.assertRaises(ValidationError):
            TotvsIntegrationConfig.objects.create(
                empresa=self.empresa,
                habilitada=True,
            )

    @override_settings(TOTVS_ENABLED=False)
    def test_kill_switch_global_bloqueia_execucao(self):
        config = self._config()
        fake = FakeTotvsAdapter()
        TotvsAdapterRegistry.register(config.produto, lambda: fake)
        operation = TotvsOperationService.preparar(
            empresa=self.empresa,
            operacao='ENVIAR_PEDIDO',
            recurso_tipo='aquisicao',
            recurso_id='10',
        )

        with self.assertRaises(TotvsConfigurationError):
            TotvsOperationService.processar(operation.pk, adapter=fake)

        operation.refresh_from_db()
        self.assertEqual(operation.status, TotvsOperation.Status.AGUARDANDO)
        self.assertEqual(fake.calls, 0)

    @override_settings(TOTVS_ENABLED=True, TOTVS_ALLOW_PRODUCTION=False)
    def test_readiness_exige_adaptador_sem_acessar_rede(self):
        config = self._config()
        result = TotvsReadinessService.avaliar(config)
        self.assertFalse(result.pronto)
        self.assertIn('Não existe adaptador instalado', ' '.join(result.bloqueios))

        TotvsAdapterRegistry.register(config.produto, FakeTotvsAdapter)
        self.assertTrue(TotvsReadinessService.avaliar(config).pronto)

    def test_preparacao_e_idempotente(self):
        first = TotvsOperationService.preparar(
            empresa=self.empresa,
            operacao='ENVIAR_PEDIDO',
            recurso_tipo='aquisicao',
            recurso_id='10',
        )
        second = TotvsOperationService.preparar(
            empresa=self.empresa,
            operacao='enviar_pedido',
            recurso_tipo='AQUISICAO',
            recurso_id=10,
        )

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(TotvsOperation.objects.count(), 1)

    @override_settings(TOTVS_ENABLED=True, TOTVS_MAX_RETRIES=3)
    def test_execucao_confirmada_grava_apenas_hashes_e_referencia(self):
        config = self._config()
        fake = FakeTotvsAdapter()
        TotvsAdapterRegistry.register(config.produto, lambda: fake)
        operation = TotvsOperationService.preparar(
            empresa=self.empresa,
            operacao='ENVIAR_PEDIDO',
            recurso_tipo='aquisicao',
            recurso_id='10',
        )

        result = TotvsOperationService.processar(operation.pk)

        self.assertEqual(result.status, TotvsOperation.Status.CONFIRMADA)
        self.assertEqual(result.referencia_remota, 'PEDIDO-123')
        attempt = TotvsOperationAttempt.objects.get(operacao=result)
        self.assertEqual(attempt.http_status, 201)
        self.assertEqual(attempt.requisicao_sha256, 'a' * 64)
        self.assertEqual(attempt.resposta_sha256, 'b' * 64)
        self.assertEqual(fake.calls, 1)

    @override_settings(TOTVS_ENABLED=True, TOTVS_MAX_RETRIES=3, TOTVS_RETRY_BASE_SECONDS=1)
    def test_falha_temporaria_agenda_retry_e_resultado_ambiguo_nao_repete(self):
        config = self._config()
        retry_adapter = FakeTotvsAdapter(TotvsRetryableError())
        TotvsAdapterRegistry.register(config.produto, lambda: retry_adapter)
        retry_operation = TotvsOperationService.preparar(
            empresa=self.empresa,
            operacao='ENVIAR_PEDIDO',
            recurso_tipo='aquisicao',
            recurso_id='11',
        )
        retry_result = TotvsOperationService.processar(retry_operation.pk)
        self.assertEqual(retry_result.status, TotvsOperation.Status.NOVA_TENTATIVA)
        self.assertIsNotNone(retry_result.proxima_tentativa_em)

        ambiguous_adapter = FakeTotvsAdapter(TotvsAmbiguousResultError())
        TotvsAdapterRegistry.register(config.produto, lambda: ambiguous_adapter)
        ambiguous_operation = TotvsOperationService.preparar(
            empresa=self.empresa,
            operacao='ENVIAR_PEDIDO',
            recurso_tipo='aquisicao',
            recurso_id='12',
        )
        ambiguous_result = TotvsOperationService.processar(ambiguous_operation.pk)
        self.assertEqual(ambiguous_result.status, TotvsOperation.Status.RECONCILIAR)
        self.assertIsNone(ambiguous_result.proxima_tentativa_em)
