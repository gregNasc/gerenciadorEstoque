from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from estoque.models import (
    Base,
    Colaborador,
    Custodia,
    DevolucaoCustodia,
    Equipamento,
    ItemCustodia,
    LinhaMovel,
)
from estoque.policies.colaboradores import ColaboradorAccessPolicy
from estoque.policies.custodias import CustodiaAccessPolicy
from estoque.services.custodia_elegibilidade_service import (
    CustodiaElegibilidadeService,
)


def _aplicar_bootstrap(form):
    for field in form.fields.values():
        css = 'form-check-input' if isinstance(field.widget, forms.CheckboxInput) else 'form-select' if isinstance(
            field.widget, (forms.Select, forms.SelectMultiple)
        ) else 'form-control'
        field.widget.attrs.setdefault('class', css)


class BaseScopedSelectMultiple(forms.SelectMultiple):
    """Expõe a Base da opção sem confiar no texto apresentado ao usuário."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(
            name, value, label, selected, index, subindex=subindex, attrs=attrs,
        )
        instance = getattr(value, 'instance', None)
        if instance is not None:
            base_id = getattr(instance, 'regional_id', None) or getattr(instance, 'base_id', None)
            empresa_id = (
                getattr(getattr(instance, 'regional', None), 'empresa_id', None)
                or getattr(instance, 'empresa_id', None)
            )
            option['attrs']['data-base-id'] = str(base_id or '')
            option['attrs']['data-empresa-id'] = str(empresa_id or '')
            if isinstance(instance, Equipamento):
                produto = instance.produto
                categoria = (getattr(produto, 'categoria', '') or '').strip()
                patrimonio = (instance.patrimonio or '').strip()
                numero_serie = (instance.numero_serie or '').strip()
                termos = (
                    str(label), categoria, patrimonio, numero_serie,
                    instance.codigo or '', getattr(produto, 'descricao', '') or '',
                    getattr(produto, 'modelo', '') or '',
                )
                option['attrs'].update({
                    'data-categoria': categoria,
                    'data-patrimonio': patrimonio,
                    'data-numero-serie': numero_serie,
                    'data-pesquisa': ' '.join(str(valor) for valor in termos if valor),
                })
        return option


class ColaboradorDocumentSelect(forms.Select):
    """Disponibiliza dados seguros para preencher o termo no navegador."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(
            name, value, label, selected, index, subindex=subindex, attrs=attrs,
        )
        instance = getattr(value, 'instance', None)
        if instance is not None:
            option['attrs'].update({
                'data-email': instance.email or '',
                'data-identificacao': instance.matricula or '',
                'data-funcao': instance.cargo_funcao or '',
            })
        return option


class ColaboradorForm(forms.ModelForm):
    class Meta:
        model = Colaborador
        fields = (
            'empresa', 'base', 'usuario', 'nome', 'email', 'telefone',
            'matricula', 'cargo_funcao', 'setor', 'ativo',
        )
        widgets = {
            'telefone': forms.TextInput(attrs={'inputmode': 'tel'}),
        }

    def __init__(self, *args, actor, **kwargs):
        self.actor = actor
        super().__init__(*args, **kwargs)
        empresas = CustodiaAccessPolicy.empresas(
            actor,
            action=CustodiaAccessPolicy.MANAGE,
        ).order_by('nome')
        self.fields['empresa'].queryset = empresas
        self.fields['base'].queryset = Base.objects.filter(
            empresa__in=empresas,
        ).select_related('empresa').order_by('empresa__nome', 'nome')
        self.fields['usuario'].queryset = User.objects.filter(
            is_active=True,
            is_superuser=False,
            perfil__empresa__in=empresas,
        ).exclude(
            colaborador_custodia__isnull=False,
        ).select_related('perfil__empresa').order_by(
            'first_name', 'last_name', 'username',
        )
        if self.instance.pk and self.instance.usuario_id:
            self.fields['usuario'].queryset = (
                self.fields['usuario'].queryset
                | User.objects.filter(pk=self.instance.usuario_id)
            ).distinct()
        self.fields['usuario'].required = False
        self.fields['usuario'].help_text = (
            'Opcional. Selecione uma conta existente ou deixe em branco para '
            'cadastrar um colaborador sem acesso ao sistema.'
        )
        self.fields['nome'].required = False
        _aplicar_bootstrap(self)

    def clean(self):
        cleaned = super().clean()
        usuario = cleaned.get('usuario')
        nome = (cleaned.get('nome') or '').strip()
        if usuario:
            nome_usuario = usuario.get_full_name().strip() or usuario.get_username()
            cleaned['nome'] = nome or nome_usuario
            cleaned['email'] = (cleaned.get('email') or usuario.email or '').strip()
        elif not nome:
            self.add_error('nome', 'Informe o nome do colaborador sem acesso.')
        empresa = cleaned.get('empresa')
        if empresa and not CustodiaAccessPolicy.empresas(
            self.actor,
            action=CustodiaAccessPolicy.MANAGE,
        ).filter(pk=empresa.pk).exists():
            self.add_error('empresa', 'Empresa fora do seu escopo de gestão.')
        return cleaned


class CustodiaForm(forms.ModelForm):
    equipamentos = forms.ModelMultipleChoiceField(
        queryset=Equipamento.objects.none(),
        required=False,
        label='Equipamentos',
        help_text=(
            'Todos os equipamentos disponíveis da Base selecionada podem ser '
            'vinculados. Equipamentos em outra Custódia vigente não aparecem.'
        ),
        widget=BaseScopedSelectMultiple(attrs={'size': 8}),
    )
    linhas_moveis = forms.ModelMultipleChoiceField(
        queryset=LinhaMovel.objects.none(),
        required=False,
        label='Chips / linhas móveis',
        widget=BaseScopedSelectMultiple(attrs={'size': 6}),
    )

    class Meta:
        model = Custodia
        fields = (
            'empresa', 'base', 'colaborador', 'modalidade_custodiante',
            'local_fisico', 'data_entrega', 'condicao_geral',
            'razao_social_responsavel', 'cnpj_responsavel',
            'custodiante_cpf', 'custodiante_identificacao',
            'custodiante_funcao_atividade', 'custodiante_email',
            'empresa_contratada', 'cnpj_contratada',
            'responsavel_entrega_nome',
            'testemunha_1_nome', 'testemunha_1_cpf', 'testemunha_1_email',
            'testemunha_2_nome', 'testemunha_2_cpf', 'testemunha_2_email',
            'observacao',
        )
        widgets = {
            'data_entrega': forms.DateInput(attrs={'type': 'date'}),
            'observacao': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, actor, equipamento_inicial=None, **kwargs):
        self.actor = actor
        super().__init__(*args, **kwargs)
        empresas = CustodiaAccessPolicy.empresas(
            actor,
            action=CustodiaAccessPolicy.MANAGE,
        ).order_by('nome')
        self.fields['empresa'].queryset = empresas
        self.fields['base'].queryset = Base.objects.filter(
            empresa__in=empresas,
        ).select_related('empresa').order_by('empresa__nome', 'nome')
        self.fields['colaborador'].queryset = ColaboradorAccessPolicy.colaboradores(
            actor,
            action=ColaboradorAccessPolicy.MANAGE,
        ).filter(ativo=True).select_related('empresa', 'base').order_by(
            'empresa__nome', 'nome',
        )
        self.fields['colaborador'].widget = ColaboradorDocumentSelect()
        self.fields['colaborador'].widget.choices = self.fields['colaborador'].choices
        self.fields['local_fisico'].queryset = self.fields[
            'local_fisico'
        ].queryset.filter(empresa__in=empresas, ativo=True).order_by(
            'empresa__nome', 'nome',
        )

        equipamentos_ids = set()
        linhas_ids = set()
        for empresa in empresas:
            equipamentos_ids.update(
                CustodiaElegibilidadeService.equipamentos(
                    empresa=empresa,
                ).exclude(
                    itens_custodia__vigente=True,
                ).values_list('pk', flat=True)
            )
            linhas_ids.update(
                CustodiaElegibilidadeService.linhas_moveis(
                    empresa=empresa,
                ).exclude(
                    itens_custodia__vigente=True,
                ).values_list('pk', flat=True)
            )
        self.fields['equipamentos'].queryset = Equipamento.objects.filter(
            pk__in=equipamentos_ids,
        ).select_related('produto', 'regional__empresa').order_by(
            'regional__empresa__nome', 'regional__nome', 'produto__descricao',
        )
        self.fields['linhas_moveis'].queryset = LinhaMovel.objects.filter(
            pk__in=linhas_ids,
        ).select_related('empresa', 'base', 'operadora').order_by(
            'empresa__nome', 'base__nome', 'numero_normalizado',
        )
        if equipamento_inicial and self.fields['equipamentos'].queryset.filter(
            pk=equipamento_inicial.pk,
        ).exists():
            self.initial.setdefault('empresa', equipamento_inicial.regional.empresa_id)
            self.initial.setdefault('base', equipamento_inicial.regional_id)
            self.initial.setdefault('equipamentos', [equipamento_inicial.pk])
        self.initial.setdefault(
            'responsavel_entrega_nome',
            actor.get_full_name().strip() or actor.get_username(),
        )
        for nome in (
            'razao_social_responsavel', 'cnpj_responsavel', 'custodiante_cpf',
            'custodiante_identificacao', 'custodiante_funcao_atividade',
            'custodiante_email', 'responsavel_entrega_nome',
            'testemunha_1_nome', 'testemunha_1_cpf', 'testemunha_1_email',
            'testemunha_2_nome', 'testemunha_2_cpf', 'testemunha_2_email',
        ):
            self.fields[nome].required = True
        self.fields['empresa_contratada'].help_text = (
            'Obrigatório somente quando a modalidade for Prestador de serviços.'
        )
        self.fields['cnpj_contratada'].help_text = (
            'Obrigatório somente quando a modalidade for Prestador de serviços.'
        )
        labels = {
            'razao_social_responsavel': 'Razão social responsável',
            'cnpj_responsavel': 'CNPJ da razão social',
            'empresa_contratada': 'Empresa contratada',
            'cnpj_contratada': 'CNPJ da contratada',
            'responsavel_entrega_nome': 'Responsável pela entrega',
            'testemunha_1_nome': 'Nome', 'testemunha_1_cpf': 'CPF',
            'testemunha_1_email': 'E-mail', 'testemunha_2_nome': 'Nome',
            'testemunha_2_cpf': 'CPF', 'testemunha_2_email': 'E-mail',
        }
        for nome, label in labels.items():
            self.fields[nome].label = label
        _aplicar_bootstrap(self)

    def clean(self):
        cleaned = super().clean()
        empresa = cleaned.get('empresa')
        base = cleaned.get('base')
        colaborador = cleaned.get('colaborador')
        local_fisico = cleaned.get('local_fisico')
        equipamentos = cleaned.get('equipamentos')
        linhas = cleaned.get('linhas_moveis')
        if not equipamentos and not linhas:
            raise ValidationError('Selecione ao menos um equipamento ou chip/linha móvel.')
        if empresa and not CustodiaAccessPolicy.empresas(
            self.actor,
            action=CustodiaAccessPolicy.MANAGE,
        ).filter(pk=empresa.pk).exists():
            self.add_error('empresa', 'Empresa fora do seu escopo de gestão.')
        if empresa and base and base.empresa_id != empresa.pk:
            self.add_error('base', 'A Base deve pertencer à empresa selecionada.')
        if empresa and colaborador and colaborador.empresa_id != empresa.pk:
            self.add_error('colaborador', 'O colaborador deve pertencer à empresa selecionada.')
        if base and colaborador and colaborador.base_id and colaborador.base_id != base.pk:
            self.add_error('colaborador', 'O colaborador está vinculado a outra Base.')
        if local_fisico and base and not local_fisico.vinculos_base.filter(base=base).exists():
            self.add_error('local_fisico', 'O local físico não está vinculado à Base selecionada.')
        for equipamento in equipamentos or ():
            if not empresa or equipamento.regional.empresa_id != empresa.pk:
                self.add_error('equipamentos', 'Há equipamento de outra empresa na seleção.')
                break
            if not base or equipamento.regional_id != base.pk:
                self.add_error('equipamentos', 'Todos os equipamentos devem pertencer à Base selecionada.')
                break
        for linha in linhas or ():
            if not empresa or linha.empresa_id != empresa.pk:
                self.add_error('linhas_moveis', 'Há linha móvel de outra empresa na seleção.')
                break
            if not base or linha.base_id != base.pk:
                self.add_error('linhas_moveis', 'Todas as linhas devem pertencer à Base selecionada.')
                break
        if cleaned.get('modalidade_custodiante') == Custodia.ModalidadeCustodiante.PRESTADOR:
            if not (cleaned.get('empresa_contratada') or '').strip():
                self.add_error('empresa_contratada', 'Informe a empresa contratada.')
            if not (cleaned.get('cnpj_contratada') or '').strip():
                self.add_error('cnpj_contratada', 'Informe o CNPJ da empresa contratada.')
        return cleaned

    def criar(self):
        custodia = self.save(commit=False)
        custodia.status = Custodia.Status.RASCUNHO
        custodia.registrado_por = self.actor
        custodia.save()
        for equipamento in self.cleaned_data['equipamentos']:
            ItemCustodia.objects.create(
                custodia=custodia,
                equipamento=equipamento,
                condicao_entrega=custodia.condicao_geral,
                acessorios_entregues=self.data.get(
                    f'acessorios_equipamento_{equipamento.pk}', '',
                ),
            )
        for linha in self.cleaned_data['linhas_moveis']:
            ItemCustodia.objects.create(
                custodia=custodia,
                linha_movel=linha,
                condicao_entrega=custodia.condicao_geral,
                acessorios_entregues=self.data.get(
                    f'acessorios_linha_{linha.pk}', '',
                ),
            )
        custodia.status = Custodia.Status.ATIVA
        custodia.save(update_fields=['status', 'atualizado_em'])
        return custodia


class DevolucaoCustodiaForm(forms.ModelForm):
    class Meta:
        model = DevolucaoCustodia
        fields = (
            'data_devolucao', 'motivo', 'responsavel_recebimento',
            'responsavel_recebimento_email', 'resultado_conferencia',
            'pendencias', 'observacao',
            'testemunha_1_nome', 'testemunha_1_cpf', 'testemunha_1_email',
            'testemunha_2_nome', 'testemunha_2_cpf', 'testemunha_2_email',
        )
        widgets = {
            'data_devolucao': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M',
            ),
            'observacao': forms.Textarea(attrs={'rows': 3}),
            'pendencias': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, actor, custodia, **kwargs):
        self.actor = actor
        self.custodia = custodia
        super().__init__(*args, **kwargs)
        self.fields['data_devolucao'].input_formats = ('%Y-%m-%dT%H:%M',)
        self.fields['responsavel_recebimento'].queryset = (
            ColaboradorAccessPolicy.colaboradores(
                actor,
                action=ColaboradorAccessPolicy.MANAGE,
            ).filter(
                empresa=custodia.empresa,
                ativo=True,
            ).order_by('nome')
        )
        self.fields['responsavel_recebimento'].widget = ColaboradorDocumentSelect()
        self.fields['responsavel_recebimento'].widget.choices = (
            self.fields['responsavel_recebimento'].choices
        )
        for nome in (
            'responsavel_recebimento_email', 'testemunha_1_nome',
            'testemunha_1_cpf', 'testemunha_1_email', 'testemunha_2_nome',
            'testemunha_2_cpf', 'testemunha_2_email',
        ):
            self.fields[nome].required = True
        for nome, label in {
            'responsavel_recebimento_email': 'E-mail do responsável pelo recebimento',
            'resultado_conferencia': 'Resultado da conferência',
            'pendencias': 'Itens ou acessórios pendentes',
            'testemunha_1_nome': 'Nome', 'testemunha_1_cpf': 'CPF',
            'testemunha_1_email': 'E-mail', 'testemunha_2_nome': 'Nome',
            'testemunha_2_cpf': 'CPF', 'testemunha_2_email': 'E-mail',
        }.items():
            self.fields[nome].label = label
        _aplicar_bootstrap(self)

    def clean(self):
        cleaned = super().clean()
        if (
            cleaned.get('resultado_conferencia')
            in (
                DevolucaoCustodia.ResultadoConferencia.RESSALVAS,
                DevolucaoCustodia.ResultadoConferencia.PARCIAL,
            )
            and not (cleaned.get('pendencias') or '').strip()
        ):
            self.add_error(
                'pendencias',
                'Descreva os itens, acessórios ou divergências pendentes.',
            )
        return cleaned
