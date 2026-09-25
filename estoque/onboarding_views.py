import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify

from estoque.models import (
    Base,
    CapacidadeRelacionamentoEmpresa,
    Empresa,
    Modulo,
    ModuloEmpresa,
    Perfil,
    RelacionamentoEmpresa,
)
from estoque.tenant_features import TenantFeatureService


SESSION_COMPANY_KEY = 'onboarding_empresa_id'
STEPS = (
    'dados',
    'modulos',
    'terminologia',
    'categorias',
    'catalogo',
    'documentacao',
    'admin',
    'bases',
    'relacionamentos',
    'revisar',
)

STEP_LABELS = {
    'dados': _('Dados básicos'),
    'modulos': _('Módulos'),
    'terminologia': _('Terminologia'),
    'categorias': _('Categorias'),
    'catalogo': _('Catálogo'),
    'documentacao': _('Documentação'),
    'admin': _('Primeiro Admin'),
    'bases': _('Bases'),
    'relacionamentos': _('Relacionamentos'),
    'revisar': _('Revisar e ativar'),
}

OPTIONAL_CONFIGURATION_NEXT = {
    'terminologia': 'categorias',
    'categorias': 'catalogo',
    'catalogo': 'documentacao',
    'documentacao': 'admin',
}


def _step_url(step, company=None):
    url = reverse('estoque:onboarding_empresa_etapa', kwargs={'etapa': step})
    if company and company.pk:
        return f'{url}?empresa={company.pk}'
    return url


def _resolve_company(request):
    company_id = request.GET.get('empresa') or request.session.get(SESSION_COMPANY_KEY)
    if not str(company_id or '').isdigit():
        return None
    company = Empresa.objects.filter(pk=company_id).first()
    if company:
        request.session[SESSION_COMPANY_KEY] = company.pk
    return company


def _password_errors(password, user):
    try:
        validate_password(password, user=user)
    except ValidationError as exc:
        return list(exc.messages)
    return []


@login_required
def onboarding_empresa(request, etapa='dados'):
    if not request.user.is_superuser:
        raise PermissionDenied('Acesso restrito ao Superuser.')

    if request.GET.get('novo') == '1':
        request.session.pop(SESSION_COMPANY_KEY, None)
        return redirect(_step_url('dados'))

    if etapa not in STEPS:
        return redirect(_step_url('dados'))

    company = _resolve_company(request)
    if etapa != 'dados' and not company:
        messages.warning(request, 'Inicie o cadastro pelos dados básicos da empresa.')
        return redirect(_step_url('dados'))
    if company and company.ativa:
        messages.info(request, f'{company.nome} já está ativa.')
        request.session.pop(SESSION_COMPANY_KEY, None)
        return redirect('estoque:painel_superuser')

    if request.method == 'POST' and request.POST.get('acao') == 'cancelar':
        request.session.pop(SESSION_COMPANY_KEY, None)
        messages.info(
            request,
            'Onboarding encerrado. O tenant incompleto permanece inativo e pode ser retomado.',
        )
        return redirect('estoque:painel_superuser')

    if request.method == 'POST':
        if etapa == 'dados':
            nome = re.sub(r'\s+', ' ', request.POST.get('nome', '').strip())
            raw_slug = request.POST.get('slug', '').strip()
            slug = slugify(raw_slug)
            duplicate = Empresa.objects.filter(nome__iexact=nome)
            if company:
                duplicate = duplicate.exclude(pk=company.pk)
            if not nome:
                messages.error(request, 'Informe o nome da empresa.')
            elif len(nome) > 200:
                messages.error(request, 'O nome da empresa deve ter no máximo 200 caracteres.')
            elif duplicate.exists():
                messages.error(request, 'Já existe uma empresa com esse nome.')
            elif raw_slug and not slug:
                messages.error(request, 'Informe um identificador de tenant válido.')
            elif slug and Empresa.objects.filter(slug__iexact=slug).exclude(
                pk=company.pk if company else None
            ).exists():
                messages.error(request, 'Este identificador de tenant já está em uso.')
            else:
                if company:
                    company.nome = nome
                    if slug:
                        company.slug = slug
                    company.save(update_fields=['nome', 'slug', 'atualizado_em'])
                else:
                    company = Empresa.objects.create(
                        nome=nome,
                        slug=slug or None,
                        ativa=False,
                    )
                request.session[SESSION_COMPANY_KEY] = company.pk
                messages.success(request, 'Dados básicos salvos. Escolha os módulos do tenant.')
                return redirect(_step_url('modulos', company))

        elif etapa == 'modulos':
            modules = list(Modulo.objects.filter(ativo=True).order_by('ordem', 'nome'))
            selected = {
                str(code).strip().lower()
                for code in request.POST.getlist('modulos')
                if str(code).strip()
            }
            valid_codes = {module.codigo for module in modules}
            if not selected:
                messages.error(request, 'Selecione pelo menos um módulo para o tenant.')
            elif not selected.issubset(valid_codes):
                messages.error(request, 'A seleção contém um módulo inválido.')
            else:
                with transaction.atomic():
                    for module in modules:
                        TenantFeatureService.configure(
                            tenant=company,
                            codigo=module.codigo,
                            enabled=module.codigo in selected,
                            actor=request.user,
                        )
                messages.success(request, 'Módulos configurados. Revise a terminologia do tenant.')
                return redirect(_step_url('terminologia', company))

        elif etapa in OPTIONAL_CONFIGURATION_NEXT:
            next_step = OPTIONAL_CONFIGURATION_NEXT[etapa]
            messages.info(
                request,
                'Etapa mantida sem alterações. Nenhuma configuração foi herdada.',
            )
            return redirect(_step_url(next_step, company))

        elif etapa == 'admin':
            existing_admin = Perfil.objects.filter(
                empresa=company,
                role=Perfil.Role.ADMIN,
                user__is_superuser=False,
            ).exists()
            if existing_admin:
                messages.info(request, 'O primeiro Admin deste tenant já está cadastrado.')
                return redirect(_step_url('bases', company))

            username = request.POST.get('username', '').strip()
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip()
            password = request.POST.get('password', '')
            confirmation = request.POST.get('password_confirmation', '')
            candidate = User(
                username=username,
                first_name=first_name,
                last_name=last_name,
                email=email,
                is_active=True,
                is_staff=False,
                is_superuser=False,
            )
            errors = []
            if not username:
                errors.append('Informe o nome de usuário do primeiro Admin.')
            elif User.objects.filter(username__iexact=username).exists():
                errors.append('Este nome de usuário já está em uso.')
            if password != confirmation:
                errors.append('A confirmação da senha não confere.')
            elif password:
                errors.extend(_password_errors(password, candidate))
            else:
                errors.append('Informe uma senha inicial segura.')
            try:
                candidate.full_clean(exclude=['password'])
            except ValidationError as exc:
                errors.extend(exc.messages)

            if errors:
                for error in dict.fromkeys(errors):
                    messages.error(request, error)
            else:
                with transaction.atomic():
                    candidate.set_password(password)
                    candidate.save()
                    profile = candidate.perfil
                    profile.empresa = company
                    profile.role = Perfil.Role.ADMIN
                    profile.save(update_fields=['empresa', 'role'])
                messages.success(
                    request,
                    f'Primeiro Admin @{candidate.username} criado sem privilégios de Superuser.',
                )
                return redirect(_step_url('bases', company))

        elif etapa == 'bases':
            raw_names = request.POST.get('bases', '')
            names = [
                re.sub(r'\s+', ' ', value.strip())
                for value in re.split(r'[;\r\n]+', raw_names)
                if value.strip()
            ]
            unique_names = list(dict.fromkeys(name.casefold() for name in names))
            normalized = []
            for unique_name in unique_names:
                normalized.append(next(name for name in names if name.casefold() == unique_name))
            if len(normalized) > 20:
                messages.error(request, 'Informe no máximo 20 bases nesta etapa.')
            elif any(len(name) > 100 for name in normalized):
                messages.error(request, 'Cada base deve ter no máximo 100 caracteres.')
            else:
                created = 0
                with transaction.atomic():
                    for name in normalized:
                        if not Base.objects.filter(empresa=company, nome__iexact=name).exists():
                            Base.objects.create(empresa=company, nome=name)
                            created += 1
                messages.success(
                    request,
                    f'Bases registradas: {created}. Esta etapa é opcional.',
                )
                return redirect(_step_url('relacionamentos', company))

        elif etapa == 'relacionamentos':
            selected_ids = {
                int(value)
                for value in request.POST.getlist('relacionamentos')
                if str(value).isdigit()
            }
            valid_ids = set(
                Empresa.objects.exclude(pk=company.pk).filter(
                    pk__in=selected_ids
                ).values_list('pk', flat=True)
            )
            if selected_ids != valid_ids:
                messages.error(request, 'A seleção contém uma empresa inválida.')
            else:
                with transaction.atomic():
                    RelacionamentoEmpresa.objects.filter(
                        empresa_origem=company,
                    ).exclude(empresa_destino_id__in=selected_ids).update(ativo=False)
                    for destination_id in selected_ids:
                        shares_support = (
                            request.POST.get(f'suporte_{destination_id}') == '1'
                        )
                        relationship, _ = RelacionamentoEmpresa.objects.update_or_create(
                            empresa_origem=company,
                            empresa_destino_id=destination_id,
                            defaults={
                                'ativo': True,
                                'compartilha_suporte_chamados': shares_support,
                                'criado_por': request.user,
                            },
                        )
                        relationship.full_clean()
                        capability, _ = CapacidadeRelacionamentoEmpresa.objects.get_or_create(
                            relacionamento=relationship,
                            recurso=CapacidadeRelacionamentoEmpresa.Recurso.CHAMADOS,
                            acao=CapacidadeRelacionamentoEmpresa.Acao.ATENDER,
                            defaults={
                                'ativo': shares_support,
                                'criado_por': request.user,
                            },
                        )
                        if capability.ativo != shares_support:
                            capability.ativo = shares_support
                            capability.criado_por = request.user
                            capability.save(update_fields=['ativo', 'criado_por', 'atualizado_em'])
                messages.success(request, 'Relacionamentos opcionais registrados.')
                return redirect(_step_url('revisar', company))

        elif etapa == 'revisar':
            explicitly_configured = ModuloEmpresa.objects.filter(
                empresa=company,
                modulo__ativo=True,
                configurado_por__isnull=False,
            ).exists()
            has_enabled_module = ModuloEmpresa.objects.filter(
                empresa=company,
                modulo__ativo=True,
                habilitado=True,
            ).exists()
            has_admin = Perfil.objects.filter(
                empresa=company,
                role=Perfil.Role.ADMIN,
                user__is_superuser=False,
                user__is_active=True,
            ).exists()
            if not explicitly_configured or not has_enabled_module:
                messages.error(request, 'Configure ao menos um módulo antes de ativar o tenant.')
                return redirect(_step_url('modulos', company))
            if not has_admin:
                messages.error(request, 'Crie um Admin ativo antes de ativar o tenant.')
                return redirect(_step_url('admin', company))
            company.ativa = True
            company.save(update_fields=['ativa', 'atualizado_em'])
            request.session.pop(SESSION_COMPANY_KEY, None)
            messages.success(request, f'Tenant {company.nome} ativado com sucesso.')
            return redirect('estoque:painel_superuser')

    module_configs = {
        config.modulo_id: config
        for config in ModuloEmpresa.objects.filter(
            empresa=company,
            modulo__ativo=True,
        ).select_related('modulo')
    } if company else {}
    modules = [
        {
            'codigo': module.codigo,
            'nome': module.nome,
            'habilitado': bool(
                module_configs.get(module.pk)
                and module_configs[module.pk].habilitado
            ),
        }
        for module in Modulo.objects.filter(ativo=True).order_by('ordem', 'nome')
    ]
    admins = list(
        User.objects.filter(
            perfil__empresa=company,
            perfil__role=Perfil.Role.ADMIN,
            is_superuser=False,
        ).order_by('date_joined')
    ) if company else []
    bases = list(company.bases.order_by('nome')) if company else []
    destinations = []
    if company:
        existing = {
            relationship.empresa_destino_id: relationship
            for relationship in RelacionamentoEmpresa.objects.filter(
                empresa_origem=company,
            )
        }
        destinations = [
            {
                'empresa': destination,
                'selecionada': bool(
                    existing.get(destination.pk) and existing[destination.pk].ativo
                ),
                'suporte': bool(
                    existing.get(destination.pk)
                    and existing[destination.pk].compartilha_suporte_chamados
                ),
            }
            for destination in Empresa.objects.exclude(pk=company.pk).order_by('nome')
        ]

    current_index = STEPS.index(etapa)
    previous_step = STEPS[current_index - 1] if current_index else None
    next_step = STEPS[current_index + 1] if current_index + 1 < len(STEPS) else None
    return render(request, 'estoque/onboarding_empresa.html', {
        'empresa_onboarding': company,
        'etapa': etapa,
        'etapas': [
            {
                'codigo': code,
                'numero': index + 1,
                'label': STEP_LABELS[code],
                'atual': index == current_index,
                'concluida': index < current_index,
                'url': _step_url(code, company) if company or code == 'dados' else '',
            }
            for index, code in enumerate(STEPS)
        ],
        'etapa_anterior_url': _step_url(previous_step, company) if previous_step else '',
        'proxima_etapa_url': _step_url(next_step, company) if next_step else '',
        'modulos_onboarding': modules,
        'admins_onboarding': admins,
        'bases_onboarding': bases,
        'destinos_relacionamento': destinations,
        'total_modulos_habilitados': sum(item['habilitado'] for item in modules),
        'relacionamentos_onboarding': (
            RelacionamentoEmpresa.objects.filter(
                empresa_origem=company,
                ativo=True,
            ).select_related('empresa_destino') if company else []
        ),
    })
