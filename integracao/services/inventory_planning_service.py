import logging

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone

from integracao.clients.inventory_planning import InventoryPlanningClient
from integracao.exceptions import InventoryPlanningError
from integracao.mappers.events import flatten_events
from integracao.models import InventoryPlanningSyncRun
from integracao.repositories.planning_repository import InventoryPlanningRepository
from integracao.services.materialization import PlanningEventMaterializer


logger = logging.getLogger("integracao.inventory_planning")


class InventoryPlanningSyncAlreadyRunning(InventoryPlanningError):
    pass


class InventoryPlanningService:
    CATALOG_ENDPOINTS = ("regions", "clients", "stores", "inventory-types")

    def __init__(self, *, client=None, repository=None, materializer=None):
        self.client = client or InventoryPlanningClient()
        self.repository = repository or InventoryPlanningRepository()
        self.materializer = materializer or PlanningEventMaterializer()

    @staticmethod
    def _start_run(endpoint, scope=None):
        try:
            with transaction.atomic():
                if InventoryPlanningSyncRun.objects.select_for_update().filter(
                    endpoint=endpoint,
                    status=InventoryPlanningSyncRun.Status.RUNNING,
                ).exists():
                    raise InventoryPlanningSyncAlreadyRunning(
                        f"Já existe sincronização em andamento para {endpoint}."
                    )
                return InventoryPlanningSyncRun.objects.create(
                    endpoint=endpoint,
                    scope=scope or {},
                )
        except IntegrityError as exc:
            if InventoryPlanningSyncRun.objects.filter(
                endpoint=endpoint,
                status=InventoryPlanningSyncRun.Status.RUNNING,
            ).exists():
                raise InventoryPlanningSyncAlreadyRunning(
                    f"Já existe sincronização em andamento para {endpoint}."
                ) from exc
            raise

    @staticmethod
    def _rate_limit_values(headers):
        def number(name):
            value = headers.get(name) if headers else None
            try:
                return int(float(value)) if value not in (None, "") else None
            except (TypeError, ValueError):
                return None

        return {
            "rate_limit_limit": number("RateLimit-Limit"),
            "rate_limit_remaining": number("RateLimit-Remaining"),
            "rate_limit_reset": number("RateLimit-Reset"),
        }

    @staticmethod
    def _finish_success(run, **counts):
        for key, value in counts.items():
            setattr(run, key, value)
        run.status = InventoryPlanningSyncRun.Status.SUCCESS
        run.finished_at = timezone.now()
        run.error_code = ""
        run.error_message = ""
        run.save()
        return run

    @staticmethod
    def _finish_failure(run, exc):
        run.status = InventoryPlanningSyncRun.Status.FAILED
        run.finished_at = timezone.now()
        run.error_code = exc.__class__.__name__[:80]
        run.error_message = (
            str(exc)[:255]
            if isinstance(exc, InventoryPlanningError)
            else "Falha inesperada; consulte o log técnico pelo identificador da execução."
        )
        run.save(update_fields=(
            "status",
            "finished_at",
            "error_code",
            "error_message",
        ))

    @staticmethod
    def _finish_interrupted(run):
        run.status = InventoryPlanningSyncRun.Status.FAILED
        run.finished_at = timezone.now()
        run.error_code = "INTERRUPTED"
        run.error_message = "Sincronização interrompida pelo operador."
        run.save(update_fields=(
            "status",
            "finished_at",
            "error_code",
            "error_message",
        ))

    def sync_catalog(self, endpoint):
        if endpoint not in self.CATALOG_ENDPOINTS:
            raise ValueError(f"Catálogo não suportado: {endpoint}")
        run = self._start_run(endpoint)
        seen = set()
        pages = created = updated = 0
        rate_limits = {}
        try:
            for items, _meta, headers in self.client.iter_pages(f"/{endpoint}"):
                pages += 1
                rate_limits = self._rate_limit_values(headers)
                page_now = timezone.now()
                for payload in items:
                    instance, was_created, was_updated = self.repository.upsert_catalog(
                        endpoint,
                        payload,
                        now=page_now,
                    )
                    seen.add(instance.external_id)
                    created += int(was_created)
                    updated += int(was_updated)
            missing = self.repository.mark_missing(endpoint, seen, now=timezone.now())
            cache.delete(f"inventory_planning:catalog:{endpoint}")
            logger.info(
                "inventory_planning_sync_success endpoint=%s pages=%s received=%s created=%s updated=%s missing=%s",
                endpoint,
                pages,
                len(seen),
                created,
                updated,
                missing,
            )
            return self._finish_success(
                run,
                pages=pages,
                received=len(seen),
                created=created,
                updated=updated,
                missing=missing,
                **rate_limits,
            )
        except KeyboardInterrupt:
            self._finish_interrupted(run)
            logger.warning(
                "inventory_planning_sync_interrupted endpoint=%s run_id=%s",
                endpoint,
                run.pk,
            )
            raise
        except Exception as exc:
            self._finish_failure(run, exc)
            logger.error(
                "inventory_planning_sync_failed endpoint=%s run_id=%s error_code=%s",
                endpoint,
                run.pk,
                exc.__class__.__name__,
            )
            raise

    def sync_events(self, *, params=None, materialize=True):
        run = self._start_run("events", scope=params)
        seen = set()
        pages = created = updated = 0
        rate_limits = {}
        try:
            for items, _meta, headers in self.client.iter_pages("/events", params=params):
                pages += 1
                rate_limits = self._rate_limit_values(headers)
                for payload in flatten_events(items):
                    instance, was_created, was_updated = self.repository.upsert_event(
                        payload,
                        now=timezone.now(),
                    )
                    seen.add(instance.external_id)
                    created += int(was_created)
                    updated += int(was_updated)
            self.repository.resolve_event_parents()
            # Ausências só são reconciliadas em snapshot global. Uma janela
            # parcial nunca pode marcar eventos fora do escopo como removidos.
            missing = 0
            if not params:
                missing = self.repository.mark_missing("events", seen, now=timezone.now())
            materialized = pending = 0
            if materialize:
                materialized, pending = self.materializer.materialize_all()
            logger.info(
                "inventory_planning_sync_success endpoint=events pages=%s received=%s created=%s updated=%s missing=%s materialized=%s pending=%s",
                pages,
                len(seen),
                created,
                updated,
                missing,
                materialized,
                pending,
            )
            return self._finish_success(
                run,
                pages=pages,
                received=len(seen),
                created=created,
                updated=updated,
                missing=missing,
                materialized=materialized,
                pending_materialization=pending,
                **rate_limits,
            )
        except KeyboardInterrupt:
            self._finish_interrupted(run)
            logger.warning(
                "inventory_planning_sync_interrupted endpoint=events run_id=%s",
                run.pk,
            )
            raise
        except Exception as exc:
            self._finish_failure(run, exc)
            logger.error(
                "inventory_planning_sync_failed endpoint=events run_id=%s error_code=%s",
                run.pk,
                exc.__class__.__name__,
            )
            raise

    def sync_all(self, *, materialize=True):
        runs = []
        for endpoint in self.CATALOG_ENDPOINTS:
            runs.append(self.sync_catalog(endpoint))
        runs.append(self.sync_events(materialize=materialize))
        return runs
