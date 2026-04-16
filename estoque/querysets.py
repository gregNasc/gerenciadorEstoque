

def filtrar_por_empresa(queryset, empresa):
    model = queryset.model

    # Equipamento
    if hasattr(model, "regional"):
        return queryset.filter(regional__empresa=empresa)

    # Transferência
    if model.__name__ == "Transferencia":
        return queryset.filter(regional_origem__empresa=empresa)

    # Histórico
    if model.__name__ == "Historico":
        return queryset.filter(equipamento__regional__empresa=empresa)

    # Sick
    if model.__name__ == "Sick":
        return queryset.filter(equipamento__regional__empresa=empresa)

    return queryset.none()