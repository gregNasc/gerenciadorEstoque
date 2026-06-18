def menu_insumos(request):

    if not request.user.is_authenticated:
        return {}

    perfil = request.user.perfil

    menu = [
        {
            "label": "Dashboard Base",
            "url": "/insumos/dashboard/base/",
            "show": True
        },
        {
            "label": "Dashboard Planejamento",
            "url": "/insumos/dashboard/planejamento/",
            "show": perfil.is_planejamento_insumos or perfil.is_admin
        },
        {
            "label": "Dashboard Financeiro",
            "url": "/insumos/dashboard/financeiro/",
            "show": perfil.is_financeiro_insumos or perfil.is_executivo_insumos or perfil.is_admin
        },
    ]

    return {
        "menu_insumos": menu
    }