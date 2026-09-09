from insumos.policies import InsumosTenantPolicy


def secure_queryset_insumos(
    queryset,
    user,
    campo_base='base',
    *,
    resource=InsumosTenantPolicy.SUPPLIES,
    action=InsumosTenantPolicy.VIEW,
):
    """Compatibilidade para consumidores antigos usando a policy da Etapa 15."""
    return InsumosTenantPolicy.queryset(
        queryset,
        user,
        base_field=campo_base,
        resource=resource,
        action=action,
    )
