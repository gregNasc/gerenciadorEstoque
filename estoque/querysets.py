from django.db.models import Q

def filtrar_por_empresa(queryset, empresa):
    model = queryset.model

    # Transferência (origem OU destino)
    if model.__name__ == "Transferencia":
        return queryset.filter(
            Q(regional_origem__empresa=empresa) |
            Q(regional_destino__empresa=empresa)
        )

    # Modelos ligados a equipamento
    if model.__name__ in ["Historico", "Sick"]:
        return queryset.filter(equipamento__regional__empresa=empresa)

    # Modelos com campo regional direto
    if any(f.name == "regional" for f in model._meta.get_fields()):
        return queryset.filter(regional__empresa=empresa)

    return queryset  # fallback seguro
