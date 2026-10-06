import re

from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.db.models import Q

from estoque.models import Base, Empresa, LinhaMovel, OperadoraMovel
from estoque.policies.linhas_moveis import LinhasMoveisAccessPolicy


class OperadoraMovelForm(forms.ModelForm):
    empresa = forms.ModelChoiceField(queryset=Empresa.objects.none())

    class Meta:
        model = OperadoraMovel
        fields = ('empresa', 'nome', 'codigo', 'ativa')
        widgets = {
            'empresa': forms.Select(attrs={'class': 'form-select'}),
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'codigo': forms.TextInput(attrs={'class': 'form-control'}),
            'ativa': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        empresas = LinhasMoveisAccessPolicy.empresas(
            user,
            action=LinhasMoveisAccessPolicy.MANAGE,
        )
        self.fields['empresa'].queryset = empresas.order_by('nome')
        if self.instance.pk:
            self.fields['empresa'].disabled = True

    def clean_empresa(self):
        empresa = self.cleaned_data['empresa']
        if not LinhasMoveisAccessPolicy.empresas(
            self.user,
            action=LinhasMoveisAccessPolicy.MANAGE,
        ).filter(pk=empresa.pk).exists():
            raise ValidationError('Empresa inexistente ou fora do escopo.')
        if self.instance.pk and empresa.pk != self.instance.empresa_id:
            raise ValidationError('A empresa da operadora não pode ser alterada.')
        return empresa

    def clean(self):
        cleaned = super().clean()
        empresa = cleaned.get('empresa')
        nome = (cleaned.get('nome') or '').strip()
        codigo = (cleaned.get('codigo') or '').strip()
        if empresa and nome and OperadoraMovel.objects.filter(
            empresa=empresa,
            nome__iexact=nome,
        ).exclude(pk=self.instance.pk).exists():
            self.add_error('nome', 'Já existe uma operadora com este nome na empresa.')
        if empresa and codigo and OperadoraMovel.objects.filter(
            empresa=empresa,
            codigo__iexact=codigo,
        ).exclude(pk=self.instance.pk).exists():
            self.add_error('codigo', 'Já existe uma operadora com este código na empresa.')
        return cleaned


class LinhaMovelForm(forms.ModelForm):
    empresa = forms.ModelChoiceField(queryset=Empresa.objects.none())
    usuario_responsavel = forms.ModelChoiceField(
        label='Usuário do sistema responsável (opcional)',
        required=False,
        queryset=User.objects.none(),
        empty_label='Sem usuário responsável',
    )

    class Meta:
        model = LinhaMovel
        fields = (
            'empresa',
            'base',
            'numero_normalizado',
            'operadora',
            'usuario_responsavel',
            'responsavel_nome',
            'iccid',
            'observacao',
        )
        labels = {
            'numero_normalizado': 'Número de telefone',
            'iccid': 'ICCID',
            'observacao': 'Observação',
        }
        widgets = {
            'empresa': forms.Select(attrs={'class': 'form-select'}),
            'base': forms.Select(attrs={'class': 'form-select'}),
            'numero_normalizado': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '(11) 99999-9999 ou +5511999999999',
                'autocomplete': 'off',
            }),
            'operadora': forms.Select(attrs={'class': 'form-select'}),
            'usuario_responsavel': forms.Select(attrs={'class': 'form-select'}),
            'responsavel_nome': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nome do colaborador sem acesso ao sistema',
            }),
            'iccid': forms.TextInput(attrs={
                'class': 'form-control',
                'inputmode': 'numeric',
                'autocomplete': 'off',
            }),
            'observacao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        empresas = LinhasMoveisAccessPolicy.empresas(
            user,
            action=LinhasMoveisAccessPolicy.MANAGE,
        ).order_by('nome')
        self.fields['empresa'].queryset = empresas

        empresa_id = None
        if self.is_bound:
            raw_empresa = self.data.get(self.add_prefix('empresa'))
            if raw_empresa and str(raw_empresa).isdigit():
                empresa_id = int(raw_empresa)
        elif self.instance.pk:
            empresa_id = self.instance.empresa_id
        elif empresas.count() == 1:
            empresa_id = empresas.values_list('pk', flat=True).first()
            self.fields['empresa'].initial = empresa_id

        empresa = empresas.filter(pk=empresa_id).first() if empresa_id else None
        base_id = None
        if self.is_bound:
            raw_base = self.data.get(self.add_prefix('base'))
            if raw_base and str(raw_base).isdigit():
                base_id = int(raw_base)
        elif self.instance.pk:
            base_id = self.instance.base_id
        bases = LinhasMoveisAccessPolicy.bases(
            user,
            action=LinhasMoveisAccessPolicy.MANAGE,
            empresa=empresa,
        )
        if empresa is None:
            bases = bases.none()
        self.fields['base'].queryset = bases
        base = self.fields['base'].queryset.filter(pk=base_id).first() if base_id else None
        self.fields['usuario_responsavel'].queryset = (
            LinhasMoveisAccessPolicy.usuarios_responsaveis(
                user,
                empresa=empresa or empresas.first(),
                base=base,
            )
            if empresas.exists()
            else User.objects.none()
        )
        operadoras = LinhasMoveisAccessPolicy.operadoras(
            user,
            action=LinhasMoveisAccessPolicy.MANAGE,
        ).filter(ativa=True)
        if empresa is not None:
            operadoras = operadoras.filter(empresa=empresa)
        else:
            operadoras = operadoras.none()
        self.fields['operadora'].queryset = operadoras.order_by('empresa__nome', 'nome')
        if self.instance.pk:
            self.fields['empresa'].disabled = True
            self.fields['operadora'].queryset = OperadoraMovel.objects.filter(
                empresa_id=self.instance.empresa_id,
            ).filter(
                Q(ativa=True) | Q(pk=self.instance.operadora_id)
            ).order_by('nome')

    def clean_numero_normalizado(self):
        valor = (self.cleaned_data.get('numero_normalizado') or '').strip()
        digitos = re.sub(r'\D', '', valor)
        if valor.startswith('+'):
            normalizado = f'+{digitos}'
        elif len(digitos) in {10, 11}:
            normalizado = f'+55{digitos}'
        elif digitos.startswith('55') and len(digitos) in {12, 13}:
            normalizado = f'+{digitos}'
        else:
            raise ValidationError('Informe um número brasileiro ou o formato internacional com +.')
        if not re.fullmatch(r'\+[1-9]\d{7,14}', normalizado):
            raise ValidationError('Informe um número válido no formato internacional.')
        return normalizado

    def clean_iccid(self):
        valor = re.sub(r'\s', '', self.cleaned_data.get('iccid') or '')
        if valor and not re.fullmatch(r'\d{18,22}', valor):
            raise ValidationError('O ICCID deve conter de 18 a 22 dígitos.')
        return valor

    def clean(self):
        cleaned = super().clean()
        empresa = cleaned.get('empresa')
        base = cleaned.get('base')
        operadora = cleaned.get('operadora')
        usuario_responsavel = cleaned.get('usuario_responsavel')
        responsavel_nome = (cleaned.get('responsavel_nome') or '').strip()
        if empresa and not LinhasMoveisAccessPolicy.empresas(
            self.user,
            action=LinhasMoveisAccessPolicy.MANAGE,
        ).filter(pk=empresa.pk).exists():
            self.add_error('empresa', 'Empresa inexistente ou fora do escopo.')
        if self.instance.pk and empresa and empresa.pk != self.instance.empresa_id:
            self.add_error('empresa', 'A empresa da linha não pode ser alterada.')
        if (
            self.instance.pk
            and base
            and base.pk != self.instance.base_id
            and self.instance.vinculos_equipamento.filter(fim_em__isnull=True).exists()
        ):
            self.add_error(
                'base',
                'Desvincule a linha do equipamento antes de alterar a Base.',
            )
        if empresa and base and base.empresa_id != empresa.pk:
            self.add_error('base', 'A Base deve pertencer à empresa selecionada.')
        if empresa and operadora and operadora.empresa_id != empresa.pk:
            self.add_error('operadora', 'A operadora deve pertencer à empresa selecionada.')
        if base and not LinhasMoveisAccessPolicy.bases(
            self.user,
            action=LinhasMoveisAccessPolicy.MANAGE,
            empresa=empresa,
        ).filter(pk=base.pk).exists():
            self.add_error('base', 'Base inexistente ou fora do escopo.')
        if empresa and usuario_responsavel and not LinhasMoveisAccessPolicy.usuarios_responsaveis(
            self.user,
            empresa=empresa,
            base=base,
        ).filter(pk=usuario_responsavel.pk).exists():
            self.add_error(
                'usuario_responsavel',
                'Usuário inexistente ou inativo.',
            )
        if usuario_responsavel and responsavel_nome:
            self.add_error(
                'responsavel_nome',
                'Escolha um usuário do sistema ou informe um colaborador sem acesso.',
            )
        return cleaned


class CredenciaisLinhaMovelForm(forms.Form):
    pin = forms.CharField(
        label='PIN', required=False, min_length=4, max_length=16,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
    )
    pin2 = forms.CharField(
        label='PIN 2', required=False, min_length=4, max_length=16,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
    )
    puk = forms.CharField(
        label='PUK', required=False, min_length=4, max_length=16,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
    )
    puk2 = forms.CharField(
        label='PUK 2', required=False, min_length=4, max_length=16,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
    )
    remover_todas = forms.BooleanField(
        label='Remover todas as credenciais armazenadas',
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('remover_todas'):
            for campo in ('pin', 'pin2', 'puk', 'puk2'):
                cleaned[campo] = ''
            return cleaned
        preenchidos = [cleaned.get(campo) for campo in ('pin', 'pin2', 'puk', 'puk2')]
        if not any(preenchidos):
            raise ValidationError('Informe ao menos uma credencial ou marque a remoção total.')
        for campo in ('pin', 'pin2', 'puk', 'puk2'):
            valor = cleaned.get(campo)
            if valor and not valor.isdigit():
                self.add_error(campo, 'Informe apenas dígitos.')
        return cleaned
