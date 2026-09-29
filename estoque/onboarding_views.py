import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify

from estoque.models import (
    Base,
    CapacidadeRelacionamentoEmpresa,
    CategoriaEquipamentoEmpresa,
    Empresa,
    Modulo,
    ModuloEmpresa,
    Perfil,
    Produto,
    RelacionamentoEmpresa,
    SecaoDocumentacaoEmpresa,
    TermoEmpresa,
)
from compras.models import CatalogoProdutoEmpresa
from estoque.services.tenant_terminology_service import TenantTerminologyService
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


def _display_value(raw_value):
    return re.sub(r'\s+', ' ', str(raw_value or '').strip())


def _terminology_keys_for_modules(module_codes):
    module_codes = set(module_codes)
    keys = {TermoEmpresa.Chave.EMPRESA}
    operational_modules = {
        Modulo.Codigo.ESTOQUE,
        Modulo.Codigo.EQUIPAMENTOS,
        Modulo.Codigo.SICK,
        Modulo.Codigo.TRANSFERENCIAS,
        Modulo.Codigo.EMPRESTIMOS,
        Modulo.Codigo.INSUMOS,
        Modulo.Codigo.CHECKLIST,
        Modulo.Codigo.CHAMADOS,
        Modulo.Codigo.ORDENS_SERVICO,
        Modulo.Codigo.CATALOGO,
        Modulo.Codigo.AUDITORIAS,
        Modulo.Codigo.CADASTROS,
    }
    if module_codes & operational_modules:
        keys.update({
            TermoEmpresa.Chave.EQUIPAMENTO,
            TermoEmpresa.Chave.BASE,
            TermoEmpresa.Chave.REGIONAL,
        })
    if Modulo.Codigo.SICK in module_codes:
        keys.add(TermoEmpresa.Chave.MANUTENCAO)
    if Modulo.Codigo.USUARIOS in module_codes:
        keys.add(TermoEmpresa.Chave.USUARIO)
    if Modulo.Codigo.DOCUMENTACAO in module_codes:
        keys.add(TermoEmpresa.Chave.DOCUMENTACAO)
    return keys


def _activation_issues(company):
    active_module_codes = set(
        Modulo.objects.filter(ativo=True).values_list('codigo', flat=True)
    )
    configured = list(
        ModuloEmpresa.objects.filter(
            empresa=company,
            modulo__ativo=True,
        ).select_related('modulo')
    )
    explicitly_configured_codes = {
        item.modulo.codigo
        for item in configured
        if item.configurado_por_id is not None
    }
    enabled_codes = {
        item.modulo.codigo for item in configured if item.habilitado
    }
    issues = []
    if explicitly_configured_codes != active_module_codes or not enabled_codes:
        issues.append({
            'step': 'modulos',
            'message': 'Revise todos os módulos e mantenha ao menos um habilitado.',
        })
    if not Perfil.objects.filter(
        empresa=company,
        role=Perfil.Role.ADMIN,
        user__is_superuser=False,
        user__is_active=True,
    ).exists():
        issues.append({
            'step': 'admin',
            'message': 'Crie ou reative o primeiro Admin antes da ativação.',
        })
    if Modulo.Codigo.DOCUMENTACAO in enabled_codes:
        sections = list(
            SecaoDocumentacaoEmpresa.objects.filter(empresa=company)
        )
        expected_codes = {
            code for code, _label in SecaoDocumentacaoEmpresa.Codigo.choices
        }
        configured_codes = {section.codigo for section in sections}
        if configured_codes != expected_codes or not any(
            section.habilitado for section in sections
        ):
            issues.append({
                'step': 'documentacao',
                'message': (
                    'Revise todas as seções de documentação e habilite '
                    'ao menos uma delas.'
                ),
            })
    return issues


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
    maintenance_mode = bool(company and company.ativa)

    documentation_module_enabled = bool(
        company
        and ModuloEmpresa.objects.filter(
            empresa=company,
            modulo__codigo=Modulo.Codigo.DOCUMENTACAO,
            modulo__ativo=True,
            habilitado=True,
        ).exists()
    )
    if etapa == 'documentacao' and not documentation_module_enabled:
        messages.info(
            request,
            'O módulo Documentação está desabilitado; a configuração foi ignorada.',
        )
        return redirect(_step_url('admin', company))

    if request.method == 'POST' and request.POST.get('acao') == 'cancelar':
        request.session.pop(SESSION_COMPANY_KEY, None)
        if maintenance_mode:
            messages.info(
                request,
                'Manutenção encerrada. As alterações salvas foram preservadas e o tenant permanece ativo.',
            )
        else:
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

        elif etapa == 'terminologia':
            module_configs = list(
                ModuloEmpresa.objects.filter(
                    empresa=company,
                    modulo__ativo=True,
                    habilitado=True,
                ).select_related('modulo')
            )
            module_names = {
                config.pk: _display_value(
                    request.POST.get(f'modulo_nome_{config.modulo.codigo}', '')
                )
                for config in module_configs
            }
            allowed_term_keys = _terminology_keys_for_modules(
                config.modulo.codigo for config in module_configs
            )
            terms = {
                key: (
                    _display_value(request.POST.get(f'termo_{key}_singular', '')),
                    _display_value(request.POST.get(f'termo_{key}_plural', '')),
                )
                for key in allowed_term_keys
            }
            errors = []
            if any(len(value) > 100 for value in module_names.values()):
                errors.append('O nome exibido de um módulo deve ter no máximo 100 caracteres.')
            if any(
                len(value) > 150
                for values in terms.values()
                for value in values
            ):
                errors.append('Cada termo deve ter no máximo 150 caracteres.')
            if errors:
                for error in errors:
                    messages.error(request, error)
            else:
                with transaction.atomic():
                    for config in module_configs:
                        config.nome_exibicao = module_names[config.pk]
                        config.save(update_fields=['nome_exibicao', 'atualizado_em'])
                    for key, (singular, plural) in terms.items():
                        if singular or plural:
                            TermoEmpresa.objects.update_or_create(
                                empresa=company,
                                chave=key,
                                defaults={
                                    'valor_singular': singular,
                                    'valor_plural': plural,
                                },
                            )
                        else:
                            TermoEmpresa.objects.filter(
                                empresa=company,
                                chave=key,
                            ).delete()
                messages.success(request, 'Terminologia do tenant salva com sucesso.')
                return redirect(_step_url('categorias', company))

        elif etapa == 'categorias':
            if request.POST.get('categories_present') != '1':
                messages.info(
                    request,
                    'Etapa mantida sem alterações. Nenhuma categoria foi herdada.',
                )
                return redirect(_step_url('catalogo', company))

            existing_categories = list(
                CategoriaEquipamentoEmpresa.objects.filter(
                    empresa=company,
                ).order_by('ordem', 'nome', 'pk')
            )
            prepared = []
            errors = []
            for category in existing_categories:
                name = _display_value(request.POST.get(
                    f'categoria_nome_{category.pk}', category.nome
                ))
                raw_order = request.POST.get(
                    f'categoria_ordem_{category.pk}', category.ordem
                )
                if not name:
                    errors.append('O nome de uma categoria existente não pode ficar vazio.')
                elif len(name) > 100:
                    errors.append('Cada categoria deve ter no máximo 100 caracteres.')
                try:
                    order = int(raw_order)
                    if order < 0 or order > 32767:
                        raise ValueError
                except (TypeError, ValueError):
                    errors.append('A ordem das categorias deve estar entre 0 e 32767.')
                    order = category.ordem
                prepared.append({
                    'object': category,
                    'name': name,
                    'order': order,
                    'active': request.POST.get(
                        f'categoria_ativa_{category.pk}'
                    ) == '1',
                })

            new_names = [
                _display_value(value)
                for value in re.split(
                    r'[;\r\n]+', request.POST.get('novas_categorias', '')
                )
                if _display_value(value)
            ]
            if any(len(name) > 100 for name in new_names):
                errors.append('Cada categoria deve ter no máximo 100 caracteres.')
            final_names = [item['name'] for item in prepared] + new_names
            normalized_names = [name.casefold() for name in final_names]
            if len(normalized_names) != len(set(normalized_names)):
                errors.append('Não repita nomes de categorias na mesma empresa.')
            if len(final_names) > 100:
                errors.append('Cadastre no máximo 100 categorias por empresa.')

            if errors:
                for error in dict.fromkeys(errors):
                    messages.error(request, error)
            else:
                now = timezone.now()
                with transaction.atomic():
                    for item in prepared:
                        category = item['object']
                        category.nome = item['name']
                        category.ordem = item['order']
                        category.ativo = item['active']
                        category.atualizado_em = now
                    if existing_categories:
                        CategoriaEquipamentoEmpresa.objects.bulk_update(
                            existing_categories,
                            ('nome', 'ordem', 'ativo', 'atualizado_em'),
                        )
                    next_order = max(
                        [item['order'] for item in prepared] or [0]
                    ) + 1
                    for offset, name in enumerate(new_names):
                        CategoriaEquipamentoEmpresa.objects.create(
                            empresa=company,
                            nome=name,
                            ativo=True,
                            ordem=next_order + offset,
                        )
                messages.success(request, 'Categorias do tenant salvas com sucesso.')
                return redirect(_step_url('catalogo', company))

        elif etapa == 'catalogo':
            next_catalog_step = (
                'documentacao' if documentation_module_enabled else 'admin'
            )
            if request.POST.get('catalog_present') != '1':
                messages.info(
                    request,
                    'Etapa mantida sem alterações. Nenhum produto foi herdado.',
                )
                return redirect(_step_url(next_catalog_step, company))

            active_categories = list(
                CategoriaEquipamentoEmpresa.objects.filter(
                    empresa=company,
                    ativo=True,
                ).order_by('ordem', 'nome', 'pk')
            )
            categories_by_name = {
                category.nome.casefold(): category.nome
                for category in active_categories
            }
            field_names = (
                'produto_codigo',
                'produto_descricao',
                'produto_fabricante',
                'produto_modelo',
                'produto_categoria',
            )
            columns = {
                field: request.POST.getlist(field)
                for field in field_names
            }
            row_count = max((len(values) for values in columns.values()), default=0)
            prepared_products = []
            errors = []
            if row_count > 25:
                errors.append('Cadastre no máximo 25 produtos por vez.')
            for index in range(min(row_count, 25)):
                row = {
                    field: _display_value(
                        columns[field][index] if index < len(columns[field]) else ''
                    )
                    for field in field_names
                }
                if not any(row.values()):
                    continue
                row['produto_codigo'] = row['produto_codigo'].upper()
                required = {
                    'produto_codigo': 'código',
                    'produto_descricao': 'descrição',
                    'produto_fabricante': 'fabricante',
                    'produto_modelo': 'modelo',
                    'produto_categoria': 'categoria',
                }
                missing = [label for field, label in required.items() if not row[field]]
                if missing:
                    errors.append(
                        f'Produto {index + 1}: preencha {", ".join(missing)}.'
                    )
                    continue
                limits = {
                    'produto_codigo': 50,
                    'produto_descricao': 255,
                    'produto_fabricante': 100,
                    'produto_modelo': 100,
                    'produto_categoria': 100,
                }
                if any(len(row[field]) > limit for field, limit in limits.items()):
                    errors.append(f'Produto {index + 1}: um campo excede o limite permitido.')
                    continue
                category_name = categories_by_name.get(
                    row['produto_categoria'].casefold()
                )
                if category_name is None:
                    errors.append(
                        f'Produto {index + 1}: selecione uma categoria ativa deste tenant.'
                    )
                    continue
                row['produto_categoria'] = category_name
                prepared_products.append(row)

            new_codes = [item['produto_codigo'].casefold() for item in prepared_products]
            if len(new_codes) != len(set(new_codes)):
                errors.append('Não repita códigos de produtos no mesmo envio.')
            if new_codes and Produto.objects.filter(
                empresa_catalogo_origem=company,
                codigo__in=[item['produto_codigo'] for item in prepared_products],
            ).exists():
                errors.append('Já existe um produto com um dos códigos informados neste tenant.')

            raw_selected_ids = request.POST.getlist('produtos_catalogo')
            if any(not str(value).isdigit() for value in raw_selected_ids):
                errors.append('A seleção contém um produto inválido.')
            selected_ids = {
                int(value) for value in raw_selected_ids if str(value).isdigit()
            }
            selected_products = list(
                Produto.objects.filter(pk__in=selected_ids, ativo=True)
            )
            valid_selected_ids = {
                product.pk
                for product in selected_products
                if product.categoria.strip().casefold() in categories_by_name
            }
            if selected_ids != valid_selected_ids:
                errors.append(
                    'Produtos compartilhados precisam estar ativos e usar uma categoria ativa deste tenant.'
                )

            if errors:
                for error in dict.fromkeys(errors):
                    messages.error(request, error)
            else:
                with transaction.atomic():
                    CatalogoProdutoEmpresa.objects.filter(
                        empresa=company,
                    ).exclude(produto_id__in=selected_ids).update(
                        ativo=False,
                        configurado_por=request.user,
                        atualizado_em=timezone.now(),
                    )
                    for product in selected_products:
                        CatalogoProdutoEmpresa.objects.update_or_create(
                            empresa=company,
                            produto=product,
                            defaults={
                                'ativo': True,
                                'configurado_por': request.user,
                            },
                        )
                    for item in prepared_products:
                        product = Produto.objects.create(
                            codigo=item['produto_codigo'],
                            descricao=item['produto_descricao'],
                            fabricante=item['produto_fabricante'],
                            modelo=item['produto_modelo'],
                            categoria=item['produto_categoria'],
                            empresa_catalogo_origem=company,
                            criado_por=request.user,
                            ativo=True,
                        )
                        CatalogoProdutoEmpresa.objects.create(
                            empresa=company,
                            produto=product,
                            ativo=True,
                            configurado_por=request.user,
                        )
                messages.success(request, 'Catálogo do tenant salvo com sucesso.')
                return redirect(_step_url(next_catalog_step, company))

        elif etapa == 'documentacao':
            if request.POST.get('documentation_present') != '1':
                messages.info(
                    request,
                    'Etapa mantida sem alterações. Nenhuma seção foi herdada.',
                )
                return redirect(_step_url('admin', company))

            section_values = {}
            errors = []
            for code, _label in SecaoDocumentacaoEmpresa.Codigo.choices:
                display_name = _display_value(
                    request.POST.get(f'secao_{code}_nome', '')
                )
                if len(display_name) > 100:
                    errors.append(
                        'O nome exibido de uma seção deve ter no máximo 100 caracteres.'
                    )
                section_values[code] = {
                    'enabled': request.POST.get(
                        f'secao_{code}_habilitada'
                    ) == '1',
                    'display_name': display_name,
                }

            if errors:
                for error in dict.fromkeys(errors):
                    messages.error(request, error)
            else:
                with transaction.atomic():
                    for code, values in section_values.items():
                        SecaoDocumentacaoEmpresa.objects.update_or_create(
                            empresa=company,
                            codigo=code,
                            defaults={
                                'habilitado': values['enabled'],
                                'nome_exibicao': values['display_name'],
                            },
                        )
                messages.success(request, 'Seções de documentação salvas com sucesso.')
                return redirect(_step_url('admin', company))

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
                    ativa=True,
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
            activation_issues = _activation_issues(company)
            if activation_issues:
                for issue in activation_issues:
                    messages.error(request, issue['message'])
                return redirect(_step_url(activation_issues[0]['step'], company))
            was_active = company.ativa
            if not was_active:
                company.ativa = True
                company.save(update_fields=['ativa', 'atualizado_em'])
            request.session.pop(SESSION_COMPANY_KEY, None)
            messages.success(
                request,
                (
                    f'Configuração de {company.nome} revisada com sucesso.'
                    if was_active
                    else f'Tenant {company.nome} ativado com sucesso.'
                ),
            )
            return redirect('estoque:painel_superuser')

    module_configs = {
        config.modulo_id: config
        for config in ModuloEmpresa.objects.filter(
            empresa=company,
            modulo__ativo=True,
        ).select_related('modulo')
    } if company else {}
    module_catalog = list(
        Modulo.objects.filter(ativo=True).order_by('ordem', 'nome')
    )
    modules = [
        {
            'codigo': module.codigo,
            'nome': module.nome,
            'nome_apresentacao': (
                module_configs[module.pk].nome_apresentacao
                if module.pk in module_configs
                else module.nome
            ),
            'habilitado': bool(
                module_configs.get(module.pk)
                and module_configs[module.pk].habilitado
            ),
        }
        for module in module_catalog
    ]
    configured_terms = {
        term.chave: term
        for term in TermoEmpresa.objects.filter(empresa=company)
    } if company else {}
    terminology_modules = [
        {
            'codigo': config.modulo.codigo,
            'padrao': config.modulo.nome,
            'valor': (
                request.POST.get(f'modulo_nome_{config.modulo.codigo}', '')
                if request.method == 'POST' and etapa == 'terminologia'
                else config.nome_exibicao
            ),
        }
        for config in module_configs.values()
        if config.habilitado
    ]
    allowed_terminology_keys = _terminology_keys_for_modules(
        item['codigo'] for item in terminology_modules
    )
    terminology_terms = [
        {
            'chave': key,
            'nome': dict(TermoEmpresa.Chave.choices)[key],
            'padrao_singular': defaults[0],
            'padrao_plural': defaults[1],
            'valor_singular': (
                request.POST.get(f'termo_{key}_singular', '')
                if request.method == 'POST' and etapa == 'terminologia'
                else getattr(configured_terms.get(key), 'valor_singular', '')
            ),
            'valor_plural': (
                request.POST.get(f'termo_{key}_plural', '')
                if request.method == 'POST' and etapa == 'terminologia'
                else getattr(configured_terms.get(key), 'valor_plural', '')
            ),
        }
        for key, defaults in TenantTerminologyService.DEFAULTS.items()
        if key in allowed_terminology_keys
    ]
    category_objects = list(
        CategoriaEquipamentoEmpresa.objects.filter(
            empresa=company,
        ).order_by('ordem', 'nome', 'pk')
    ) if company else []
    onboarding_categories = [
        {
            'id': category.pk,
            'nome': (
                request.POST.get(f'categoria_nome_{category.pk}', category.nome)
                if request.method == 'POST' and etapa == 'categorias'
                else category.nome
            ),
            'ordem': (
                request.POST.get(f'categoria_ordem_{category.pk}', category.ordem)
                if request.method == 'POST' and etapa == 'categorias'
                else category.ordem
            ),
            'ativa': (
                request.POST.get(f'categoria_ativa_{category.pk}') == '1'
                if request.method == 'POST' and etapa == 'categorias'
                else category.ativo
            ),
        }
        for category in category_objects
    ]
    active_category_names = [
        category.nome for category in category_objects if category.ativo
    ]
    catalog_product_query = Q(pk__in=[])
    for category_name in active_category_names:
        catalog_product_query |= Q(categoria__iexact=category_name)
    catalog_links = {
        link.produto_id: link
        for link in CatalogoProdutoEmpresa.objects.filter(
            empresa=company,
        ).select_related('produto')
    } if company else {}
    catalog_products = list(
        Produto.objects.filter(catalog_product_query, ativo=True)
        .select_related('empresa_catalogo_origem')
        .order_by('categoria', 'descricao', 'codigo', 'pk')
    ) if company and active_category_names else []
    onboarding_catalog_products = [
        {
            'produto': product,
            'selecionado': (
                str(product.pk) in request.POST.getlist('produtos_catalogo')
                if request.method == 'POST' and etapa == 'catalogo'
                else bool(catalog_links.get(product.pk) and catalog_links[product.pk].ativo)
            ),
            'proprio': product.empresa_catalogo_origem_id == company.pk,
        }
        for product in catalog_products
    ]
    new_catalog_rows = []
    if request.method == 'POST' and etapa == 'catalogo':
        posted_catalog_columns = {
            field: request.POST.getlist(field)
            for field in (
                'produto_codigo', 'produto_descricao', 'produto_fabricante',
                'produto_modelo', 'produto_categoria',
            )
        }
        posted_row_count = max(
            (len(values) for values in posted_catalog_columns.values()),
            default=0,
        )
        for index in range(min(posted_row_count, 25)):
            new_catalog_rows.append({
                field: (
                    values[index] if index < len(values) else ''
                )
                for field, values in posted_catalog_columns.items()
            })
    if not new_catalog_rows:
        new_catalog_rows = [{}]
    configured_documentation_sections = {
        section.codigo: section
        for section in SecaoDocumentacaoEmpresa.objects.filter(
            empresa=company,
        )
    } if company else {}
    onboarding_documentation_sections = [
        {
            'codigo': code,
            'padrao': label,
            'habilitada': (
                request.POST.get(f'secao_{code}_habilitada') == '1'
                if request.method == 'POST' and etapa == 'documentacao'
                else bool(
                    configured_documentation_sections.get(code)
                    and configured_documentation_sections[code].habilitado
                )
            ),
            'nome_exibicao': (
                request.POST.get(f'secao_{code}_nome', '')
                if request.method == 'POST' and etapa == 'documentacao'
                else getattr(
                    configured_documentation_sections.get(code),
                    'nome_exibicao',
                    '',
                )
            ),
        }
        for code, label in SecaoDocumentacaoEmpresa.Codigo.choices
    ]
    admins = list(
        User.objects.filter(
            perfil__empresa=company,
            perfil__role=Perfil.Role.ADMIN,
            is_superuser=False,
            is_active=True,
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
            for destination in Empresa.objects.filter(ativa=True).exclude(
                pk=company.pk
            ).order_by('nome')
        ]

    review_enabled_modules = [item for item in modules if item['habilitado']]
    review_disabled_modules = [item for item in modules if not item['habilitado']]
    resolved_terms = TenantTerminologyService.labels(company) if company else {}
    review_terms = [
        {
            'chave': key,
            'nome': dict(TermoEmpresa.Chave.choices)[key],
            'singular': resolved_terms[key]['singular'],
            'plural': resolved_terms[key]['plural'],
            'personalizado': key in configured_terms,
        }
        for key in TenantTerminologyService.DEFAULTS
        if company and key in allowed_terminology_keys
    ]
    active_category_keys = {
        name.casefold() for name in active_category_names
    }
    review_catalog_products = [
        link.produto
        for link in CatalogoProdutoEmpresa.objects.filter(
            empresa=company,
            ativo=True,
            produto__ativo=True,
        ).select_related('produto', 'produto__empresa_catalogo_origem').order_by(
            'produto__categoria', 'produto__descricao', 'produto__codigo'
        )
        if link.produto.categoria.strip().casefold() in active_category_keys
    ] if company else []
    review_documentation_sections = [
        {
            'codigo': item['codigo'],
            'nome': item['nome_exibicao'].strip() or item['padrao'],
        }
        for item in onboarding_documentation_sections
        if item['habilitada']
    ]
    review_relationships = list(
        RelacionamentoEmpresa.objects.filter(
            empresa_origem=company,
            empresa_destino__ativa=True,
            ativo=True,
        ).select_related('empresa_destino').order_by('empresa_destino__nome')
    ) if company else []
    activation_issues = _activation_issues(company) if company else []

    current_index = STEPS.index(etapa)
    previous_step = STEPS[current_index - 1] if current_index else None
    next_step = STEPS[current_index + 1] if current_index + 1 < len(STEPS) else None
    return render(request, 'estoque/onboarding_empresa.html', {
        'empresa_onboarding': company,
        'modo_manutencao': maintenance_mode,
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
        'modulos_terminologia': terminology_modules,
        'termos_terminologia': terminology_terms,
        'categorias_onboarding': onboarding_categories,
        'categorias_catalogo_onboarding': active_category_names,
        'produtos_catalogo_onboarding': onboarding_catalog_products,
        'novos_produtos_catalogo': new_catalog_rows,
        'secoes_documentacao_onboarding': onboarding_documentation_sections,
        'modulo_documentacao_habilitado': documentation_module_enabled,
        'novas_categorias_onboarding': (
            request.POST.get('novas_categorias', '')
            if request.method == 'POST' and etapa == 'categorias'
            else ''
        ),
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
        'modulos_habilitados_revisao': review_enabled_modules,
        'modulos_desabilitados_revisao': review_disabled_modules,
        'terminologia_revisao': review_terms,
        'categorias_ativas_revisao': [
            category for category in category_objects if category.ativo
        ],
        'total_categorias_inativas_revisao': sum(
            not category.ativo for category in category_objects
        ),
        'produtos_revisao': review_catalog_products,
        'secoes_documentacao_revisao': review_documentation_sections,
        'relacionamentos_revisao': review_relationships,
        'pendencias_ativacao': activation_issues,
        'pronto_para_ativar': not activation_issues,
        'admin_anterior_url': _step_url(
            'documentacao' if documentation_module_enabled else 'catalogo',
            company,
        ) if company else '',
    })
