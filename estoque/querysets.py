from django.db.models import Q

def filtrar_por_empresa(queryset, empresa):
    model = queryset.model

    # Transferência (origem OU destino)
    if model.__name__ == "Transferencia":
        return queryset.filter(
            Q(regional_origem__empresa=empresa) |
            Q(regional_destino__empresa=empresa)
        )
    if model.__name__ == "Sick":
        return queryset.filter(
            Q(equipamento__regional__empresa=empresa)
            | Q(ativo_insumo__base__empresa=empresa)
        )
    if model.__name__ == "Historico":
        return queryset.filter(equipamento__regional__empresa=empresa)

    if any(f.name == "regional" for f in model._meta.get_fields()):
        return queryset.filter(regional__empresa=empresa)

