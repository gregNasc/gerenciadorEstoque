import hashlib
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from integracao.exceptions import (
    TotvsAmbiguousResultError,
    TotvsConfigurationError,
    TotvsError,
    TotvsRetryableError,
)
from integracao.models import (
    TotvsIntegrationConfig,
    TotvsOperation,
    TotvsOperationAttempt,
)
from integracao.totvs.readiness import TotvsReadinessService
from integracao.totvs.registry import TotvsAdapterRegistry


logger = logging.getLogger('integracao.totvs')


class TotvsOperationService:
    @classmethod
    def preparar(
        cls, *, empresa, operacao, recurso_tipo, recurso_id,
        versao_payload=1, criado_por=None,
    ):
        operation_code = (operacao or '').strip().upper()
        resource_type = (recurso_tipo or '').strip().lower()
        resource_id = str(recurso_id).strip()
        identity = '|'.join((
            str(empresa.pk), operation_code, resource_type, resource_id,
            str(versao_payload),
        ))
        idempotency_key = hashlib.sha256(identity.encode('utf-8')).hexdigest()
        operation, _ = TotvsOperation.objects.get_or_create(
            idempotency_key=idempotency_key,
            defaults={
                'empresa': empresa,
                'operacao': operation_code,
                'recurso_tipo': resource_type,
                'recurso_id': resource_id,
                'versao_payload': versao_payload,
                'criado_por': criado_por,
            },
        )
        return operation

    @classmethod
    def processar(cls, operation_id, *, adapter=None):
        operation = TotvsOperation.objects.select_related('empresa').get(pk=operation_id)
        try:
            config = operation.empresa.configuracao_totvs
        except TotvsIntegrationConfig.DoesNotExist:
            config = None
        readiness = TotvsReadinessService.avaliar(config)
        if not readiness.pronto:
            raise TotvsConfigurationError(' '.join(readiness.bloqueios))

        with transaction.atomic():
            operation = TotvsOperation.objects.select_for_update().get(pk=operation_id)
            if operation.status in {
                TotvsOperation.Status.ENVIADA,
                TotvsOperation.Status.CONFIRMADA,
                TotvsOperation.Status.CANCELADA,
            }:
                return operation
            if operation.status == TotvsOperation.Status.PROCESSANDO:
                return operation
            operation.status = TotvsOperation.Status.PROCESSANDO
            operation.tentativas += 1
            operation.iniciada_em = timezone.now()
            operation.proxima_tentativa_em = None
            operation.save()
            attempt_number = operation.tentativas

        api = adapter or TotvsAdapterRegistry.build(config.produto)
        try:
            result = api.enviar(config=config, operacao=operation)
        except TotvsAmbiguousResultError:
            return cls._registrar_falha(
                operation, attempt_number,
                status=TotvsOperation.Status.RECONCILIAR,
                codigo='RESULTADO_AMBIGUO',
                mensagem='A operação exige reconciliação antes de um novo envio.',
            )
        except TotvsRetryableError as exc:
            max_retries = max(int(getattr(settings, 'TOTVS_MAX_RETRIES', 3)), 1)
            if attempt_number >= max_retries:
                return cls._registrar_falha(
                    operation, attempt_number,
                    status=TotvsOperation.Status.FALHOU,
                    codigo='LIMITE_TENTATIVAS',
                    mensagem='A operação atingiu o limite de tentativas.',
                )
            delay = exc.retry_after_seconds or (
                int(getattr(settings, 'TOTVS_RETRY_BASE_SECONDS', 60))
                * (2 ** (attempt_number - 1))
            )
            return cls._registrar_falha(
                operation, attempt_number,
                status=TotvsOperation.Status.NOVA_TENTATIVA,
                codigo=type(exc).__name__,
                mensagem='Falha temporária; uma nova tentativa poderá ser executada.',
                proxima_tentativa_em=timezone.now() + timedelta(seconds=delay),
            )
        except TotvsError as exc:
            return cls._registrar_falha(
                operation, attempt_number,
                status=TotvsOperation.Status.FALHOU,
                codigo=type(exc).__name__,
                mensagem='A integração recusou a operação.',
            )
        except Exception:
            logger.exception('totvs_unexpected_error operation=%s', operation.pk)
            return cls._registrar_falha(
                operation, attempt_number,
                status=TotvsOperation.Status.FALHOU,
                codigo='ERRO_INTERNO',
                mensagem='Falha interna; consulte os registros técnicos.',
            )

        now = timezone.now()
        with transaction.atomic():
            operation = TotvsOperation.objects.select_for_update().get(pk=operation.pk)
            operation.status = (
                TotvsOperation.Status.CONFIRMADA
                if result.confirmado else TotvsOperation.Status.ENVIADA
            )
            operation.referencia_remota = result.referencia_remota
            operation.status_remoto = result.status_remoto
            operation.finalizada_em = now
            operation.ultimo_erro_codigo = ''
            operation.ultimo_erro_mensagem = ''
            operation.save()
            TotvsOperationAttempt.objects.create(
                operacao=operation,
                numero=attempt_number,
                resultado=operation.status,
                http_status=result.http_status,
                requisicao_sha256=result.requisicao_sha256,
                resposta_sha256=result.resposta_sha256,
                finalizada_em=now,
            )
        return operation

    @staticmethod
    def _registrar_falha(
        operation, attempt_number, *, status, codigo, mensagem,
        proxima_tentativa_em=None,
    ):
        now = timezone.now()
        with transaction.atomic():
            operation = TotvsOperation.objects.select_for_update().get(pk=operation.pk)
            operation.status = status
            operation.finalizada_em = now
            operation.proxima_tentativa_em = proxima_tentativa_em
            operation.ultimo_erro_codigo = codigo
            operation.ultimo_erro_mensagem = mensagem
            operation.save()
            TotvsOperationAttempt.objects.create(
                operacao=operation,
                numero=attempt_number,
                resultado=status,
                erro_codigo=codigo,
                finalizada_em=now,
            )
        return operation
