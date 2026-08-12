from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from estoque.models import Base
from insumos.models import Cliente
from integracao.models import (
    BindingSource,
    PlanningClient,
    PlanningClientBinding,
    PlanningEvent,
    PlanningInventoryType,
    PlanningOperationalBaseBinding,
    PlanningRegion,
    PlanningRegionBinding,
)
from integracao.services.binding_suggestions import (
    is_oxxo_client,
    suggest_local_clients,
    suggest_operational_bases,
)
from integracao.services.materialization import PlanningEventMaterializer
from integracao.services.operational_base_resolver import (
    OperationalBaseResolver,
    PlanningClientResolver,
)


def _pending_parent_events():
    return PlanningEvent.objects.filter(
        inventory_type__kind=PlanningInventoryType.Kind.PARENT,
        materialization_status=PlanningEvent.MaterializationStatus.PENDING,
    )

def _confirm_client(planning_client, local_client, user, source):
    binding, _created = PlanningClientBinding.objects.update_or_create(
        planning_client=planning_client,
        defaults={
            "local_client": local_client,
            "confirmed_by": user,
            "confirmed_at": timezone.now(),
            "source": source,
            "is_active": True,
        },
    )
    return binding

def _confirm_operational_base(planning_client, planning_region, local_base, user, source, reason):
    binding, _created = PlanningOperationalBaseBinding.objects.update_or_create(
        planning_client=planning_client,
        planning_region=planning_region,
        defaults={
            "local_base": local_base,
            "confirmed_by": user,
            "confirmed_at": timezone.now(),
            "source": source,
            "reason": reason[:255],
            "is_active": True,
        },
    )
    return binding

def _confirm_region_fallback(planning_region, local_base, user, source):
    binding, _created = PlanningRegionBinding.objects.update_or_create(
        planning_region=planning_region,
        defaults={
            "local_base": local_base,
            "confirmed_by": user,
            "confirmed_at": timezone.now(),
            "source": source,
            "is_active": True,
        },
    )
    return binding

@login_required
@permission_required("integracao.gerenciar_mapeamentos_planning", raise_exception=True)
def planning_mappings(request):
    if request.method == "POST":
        action = request.POST.get("action", "")
        with transaction.atomic():
            if action == "confirm_client":
                planning_client = get_object_or_404(
                    PlanningClient,
                    pk=request.POST.get("planning_client"),
                )
                local_client = get_object_or_404(
                    Cliente,
                    pk=request.POST.get("local_client"),
                    ativo=True,
                )
                suggestion = suggest_local_clients(planning_client)
                suggested = bool(
                    suggestion.best
                    and suggestion.best.instance.pk == local_client.pk
                )
                _confirm_client(
                    planning_client,
                    local_client,
                    request.user,
                    BindingSource.SUGGESTED if suggested else BindingSource.MANUAL,
                )
                messages.success(request, "Vínculo de cliente confirmado.")
            elif action == "bulk_confirm_clients":
                confirmed = 0
                for planning_client in PlanningClient.objects.filter(
                    pk__in=request.POST.getlist("planning_clients"),
                ):
                    suggestion = suggest_local_clients(planning_client)
                    if not suggestion.can_bulk_confirm:
                        continue
                    _confirm_client(
                        planning_client,
                        suggestion.best.instance,
                        request.user,
                        BindingSource.RULE,
                    )
                    confirmed += 1
                messages.success(request, f"Clientes confirmados em lote: {confirmed}.")
            elif action == "confirm_operational_base":
                planning_client = get_object_or_404(
                    PlanningClient,
                    pk=request.POST.get("planning_client"),
                )
                planning_region = get_object_or_404(
                    PlanningRegion,
                    pk=request.POST.get("planning_region"),
                )
                local_base = get_object_or_404(Base, pk=request.POST.get("local_base"))
                client_resolution = PlanningClientResolver.resolve(planning_client)
                if not client_resolution.local_client:
                    messages.error(request, "Confirme o cliente antes da base operacional.")
                    return redirect("integracao:planning_mappings")
                suggestion = suggest_operational_bases(
                    planning_region,
                    client_resolution.local_client,
                )
                suggested = bool(
                    suggestion.best
                    and suggestion.best.instance.pk == local_base.pk
                )
                reason = (
                    suggestion.best.reason
                    if suggested
                    else "Base escolhida manualmente por usuário autorizado."
                )
                _confirm_operational_base(
                    planning_client,
                    planning_region,
                    local_base,
                    request.user,
                    BindingSource.SUGGESTED if suggested else BindingSource.MANUAL,
                    reason,
                )
                messages.success(request, "Base operacional confirmada.")
            elif action == "bulk_confirm_operational_bases":
                confirmed = 0
                for pair in request.POST.getlist("operational_pairs"):
                    try:
                        client_id, region_id = (int(value) for value in pair.split(":"))
                    except (TypeError, ValueError):
                        continue
                    planning_client = PlanningClient.objects.filter(pk=client_id).first()
                    planning_region = PlanningRegion.objects.filter(pk=region_id).first()
                    if not planning_client or not planning_region:
                        continue
                    client_resolution = PlanningClientResolver.resolve(planning_client)
                    if not client_resolution.local_client:
                        continue
                    suggestion = suggest_operational_bases(
                        planning_region,
                        client_resolution.local_client,
                    )
                    if not suggestion.can_bulk_confirm:
                        continue
                    _confirm_operational_base(
                        planning_client,
                        planning_region,
                        suggestion.best.instance,
                        request.user,
                        BindingSource.RULE,
                        suggestion.best.reason,
                    )
                    confirmed += 1
                messages.success(request, f"Bases confirmadas em lote: {confirmed}.")
            elif action == "confirm_region_fallback":
                planning_client = get_object_or_404(
                    PlanningClient,
                    pk=request.POST.get("planning_client"),
                )
                planning_region = get_object_or_404(
                    PlanningRegion,
                    pk=request.POST.get("planning_region"),
                )
                client_resolution = PlanningClientResolver.resolve(planning_client)
                if not client_resolution.local_client:
                    messages.error(request, "Confirme o cliente antes do fallback regional.")
                    return redirect("integracao:planning_mappings")
                suggestion = suggest_operational_bases(
                    planning_region,
                    client_resolution.local_client,
                )
                allowed = bool(
                    OperationalBaseResolver.region_is_unambiguous(planning_region)
                    and suggestion.best
                    and suggestion.best.score >= 80
                    and not suggestion.ambiguous
                )
                if not allowed:
                    messages.error(
                        request,
                        "A regional não é inequívoca para fallback; confirme o vínculo combinado.",
                    )
                    return redirect("integracao:planning_mappings")
                _confirm_region_fallback(
                    planning_region,
                    suggestion.best.instance,
                    request.user,
                    BindingSource.RULE,
                )
                messages.success(request, "Fallback regional inequívoco confirmado.")
            elif action == "deactivate_binding":
                models = {
                    "client": PlanningClientBinding,
                    "region": PlanningRegionBinding,
                    "operational": PlanningOperationalBaseBinding,
                }
                model = models.get(request.POST.get("binding_type"))
                if not model:
                    raise PermissionDenied
                binding = get_object_or_404(model, pk=request.POST.get("binding_id"))
                binding.is_active = False
                binding.confirmed_by = request.user
                binding.save(update_fields=("is_active", "confirmed_by", "updated_at"))
                messages.success(request, "Vínculo desativado sem excluir o histórico.")
            elif action == "materialize_resolved":
                if not request.user.has_perm("integracao.executar_materializacao_planning"):
                    raise PermissionDenied
                materialized, pending = PlanningEventMaterializer().materialize_all(
                    resolved_only=True,
                )
                messages.success(
                    request,
                    f"Materialização controlada concluída: {materialized} criado(s), "
                    f"{pending} pendência(s) entre os resolvidos.",
                )
            else:
                messages.error(request, "Ação de mapeamento inválida.")
        return redirect("integracao:planning_mappings")

    search = request.GET.get("q", "").strip()
    client_filter = request.GET.get("client", "")
    region_filter = request.GET.get("region", "")
    operation_filter = request.GET.get("operation", "")
    error_filter = request.GET.get("pending", "")

    pending_events = _pending_parent_events()
    if search:
        pending_events = pending_events.filter(
            Q(client__trade_name__icontains=search)
            | Q(client__corporate_name__icontains=search)
            | Q(region__name__icontains=search)
            | Q(store__code__icontains=search)
        )
    if client_filter.isdigit():
        pending_events = pending_events.filter(client_id=int(client_filter))
    if region_filter.isdigit():
        pending_events = pending_events.filter(region_id=int(region_filter))
    if error_filter:
        pending_events = pending_events.filter(materialization_error=error_filter)

    client_counts = {
        row["client_id"]: row["events"]
        for row in pending_events.exclude(client_id=None).values("client_id").annotate(
            events=Count("id"),
        )
    }
    client_rows = []
    for planning_client in PlanningClient.objects.filter(
        pk__in=client_counts,
    ).order_by("trade_name", "corporate_name")[:100]:
        resolution = PlanningClientResolver.resolve(planning_client)
        if resolution.binding:
            continue
        suggestion = suggest_local_clients(planning_client)
        if operation_filter == "oxxo" and not (
            "OXXO" in f"{planning_client.trade_name} {planning_client.corporate_name}".upper()
            or (suggestion.best and is_oxxo_client(suggestion.best.instance))
        ):
            continue
        client_rows.append({
            "planning_client": planning_client,
            "suggestion": suggestion,
            "events": client_counts[planning_client.pk],
        })

    pair_counts = {
        (row["client_id"], row["region_id"]): row["events"]
        for row in pending_events.exclude(client_id=None).exclude(region_id=None).values(
            "client_id", "region_id"
        ).annotate(events=Count("id"))
    }
    base_rows = []
    for (client_id, region_id), events in list(pair_counts.items())[:200]:
        planning_client = PlanningClient.objects.get(pk=client_id)
        planning_region = PlanningRegion.objects.get(pk=region_id)
        client_resolution = PlanningClientResolver.resolve(planning_client)
        if not client_resolution.local_client:
            continue
        if operation_filter == "oxxo" and not is_oxxo_client(client_resolution.local_client):
            continue
        existing = PlanningOperationalBaseBinding.objects.filter(
            planning_client=planning_client,
            planning_region=planning_region,
            is_active=True,
        ).exists()
        if existing:
            continue
        suggestion = suggest_operational_bases(
            planning_region,
            client_resolution.local_client,
        )
        base_rows.append({
            "planning_client": planning_client,
            "local_client": client_resolution.local_client,
            "planning_region": planning_region,
            "suggestion": suggestion,
            "allow_region_fallback": bool(
                OperationalBaseResolver.region_is_unambiguous(planning_region)
                and suggestion.best
                and suggestion.best.score >= 80
                and not suggestion.ambiguous
            ),
            "events": events,
        })

    pending_breakdown = list(
        PlanningEvent.objects.filter(
            materialization_status=PlanningEvent.MaterializationStatus.PENDING,
        ).values("materialization_error").annotate(total=Count("id")).order_by("materialization_error")
    )
    stats = {
        "events": PlanningEvent.objects.count(),
        "parents": PlanningEvent.objects.filter(
            inventory_type__kind=PlanningInventoryType.Kind.PARENT,
        ).count(),
        "children": PlanningEvent.objects.filter(
            inventory_type__kind=PlanningInventoryType.Kind.CHILD,
        ).count(),
        "materialized": PlanningEvent.objects.filter(
            materialization_status=PlanningEvent.MaterializationStatus.MATERIALIZED,
        ).count(),
        "pending": PlanningEvent.objects.filter(
            materialization_status=PlanningEvent.MaterializationStatus.PENDING,
        ).count(),
        "errors": PlanningEvent.objects.filter(
            materialization_status=PlanningEvent.MaterializationStatus.ERROR,
        ).count(),
    }
    return render(request, "integracao/planning_mappings.html", {
        "client_rows": client_rows,
        "base_rows": base_rows,
        "client_bindings": PlanningClientBinding.objects.select_related(
            "planning_client", "local_client", "confirmed_by"
        ).order_by("-is_active", "planning_client__trade_name")[:100],
        "operational_bindings": PlanningOperationalBaseBinding.objects.select_related(
            "planning_client", "planning_region", "local_base", "confirmed_by"
        ).order_by("-is_active", "planning_client__trade_name", "planning_region__name")[:200],
        "region_bindings": PlanningRegionBinding.objects.select_related(
            "planning_region", "local_base", "confirmed_by"
        ).order_by("-is_active", "planning_region__name")[:100],
        "local_clients": Cliente.objects.filter(ativo=True).order_by("sigla", "nome"),
        "local_bases": Base.objects.all().order_by("nome"),
        "planning_clients": PlanningClient.objects.filter(events__isnull=False).distinct().order_by("trade_name"),
        "planning_regions": PlanningRegion.objects.filter(events__isnull=False).distinct().order_by("name"),
        "pending_breakdown": pending_breakdown,
        "stats": stats,
        "filters": {
            "q": search,
            "client": client_filter,
            "region": region_filter,
            "operation": operation_filter,
            "pending": error_filter,
        },
    })
