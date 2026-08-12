from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from estoque.models import Base

from .models import AuditoriaBase, CampanhaAuditoria


class CampanhaAuditoriaForm(forms.ModelForm):
    class Meta:
        model = CampanhaAuditoria
        fields = ['empresa', 'nome', 'descricao', 'instrucoes']
        widgets = {
            'empresa': forms.Select(attrs={'class': 'form-select'}),
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'descricao': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'instrucoes': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
        }

class CampanhaAuditoriaEdicaoForm(CampanhaAuditoriaForm):
    justificativa = forms.CharField(
        label=_('Justificativa da alteração'),
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        help_text=_('Obrigatória quando a campanha já saiu do rascunho.'),
    )


class AuditoriaBasesLoteForm(forms.Form):
    bases = forms.ModelMultipleChoiceField(
        label=_('Bases'),
        queryset=Base.objects.none(),
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': 8}),
    )
    inicio_em = forms.DateTimeField(
        label=_('Início'),
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(
            attrs={'type': 'datetime-local', 'class': 'form-control'},
            format='%Y-%m-%dT%H:%M',
        ),
    )
    fim_em = forms.DateTimeField(
        label=_('Fim'),
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(
            attrs={'type': 'datetime-local', 'class': 'form-control'},
            format='%Y-%m-%dT%H:%M',
        ),
    )
    observacoes = forms.CharField(
        label=_('Observações'),
        required=False,
        widget=forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
    )
    justificativa = forms.CharField(
        label=_('Justificativa'),
        required=False,
        widget=forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        help_text=_('Obrigatória para inclusão depois do início da campanha.'),
    )

    def __init__(self, *args, empresa=None, campanha=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Base.objects.filter(empresa=empresa).order_by('nome') if empresa else Base.objects.none()
        if campanha:
            qs = qs.exclude(auditorias__campanha=campanha)
        self.fields['bases'].queryset = qs

    def clean(self):
        dados = super().clean()
        inicio = dados.get('inicio_em')
        fim = dados.get('fim_em')
        if inicio and fim:
            auditoria = AuditoriaBase(inicio_em=inicio, fim_em=fim)
            try:
                auditoria.clean()
            except ValidationError as exc:
                self.add_error(None, exc)
        return dados
class AuditoriaBaseForm(forms.ModelForm):
    class Meta:
        model = AuditoriaBase
        fields = ['base', 'inicio_em', 'fim_em', 'observacoes']
        widgets = {
            'base': forms.Select(attrs={'class': 'form-select'}),
            'inicio_em': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}, format='%Y-%m-%dT%H:%M'),
            'fim_em': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}, format='%Y-%m-%dT%H:%M'),
            'observacoes': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }

    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['base'].queryset = Base.objects.filter(empresa=empresa) if empresa else Base.objects.none()
        self.fields['inicio_em'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['fim_em'].input_formats = ['%Y-%m-%dT%H:%M']

class PeriodoAuditoriaBaseForm(forms.Form):
    inicio_em = forms.DateTimeField(
        label=_('Início'),
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(
            attrs={'type': 'datetime-local', 'class': 'form-control'},
            format='%Y-%m-%dT%H:%M',
        ),
    )
    fim_em = forms.DateTimeField(
        label=_('Fim'),
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(
            attrs={'type': 'datetime-local', 'class': 'form-control'},
            format='%Y-%m-%dT%H:%M',
        ),
    )
    justificativa = forms.CharField(
        label=_('Justificativa'),
        required=False,
        widget=forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
    )

    def clean(self):
        dados = super().clean()
        inicio = dados.get('inicio_em')
        fim = dados.get('fim_em')
        if inicio and fim:
            auditoria = AuditoriaBase(inicio_em=inicio, fim_em=fim)
            try:
                auditoria.clean()
            except ValidationError as exc:
                self.add_error(None, exc)
        return dados
class RegularizacaoForm(forms.Form):
    justificativa = forms.CharField(
        label=_('Justificativa'),
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
    )

class SolicitarCorrecaoForm(forms.Form):
    prazo_correcao_em = forms.DateTimeField(
        label=_('Prazo para correção'),
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(
            attrs={'type': 'datetime-local', 'class': 'form-control'},
            format='%Y-%m-%dT%H:%M',
        ),
    )
    orientacoes_correcao = forms.CharField(
        label=_('Orientações para a base'),
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
    )

class RespostaDivergenciaForm(forms.Form):
    justificativa_base = forms.CharField(
        label=_('Justificativa ou providência adotada'),
        widget=forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
    )

class TransferenciaAuditoriaForm(RegularizacaoForm):
    base_destino = forms.ModelChoiceField(queryset=Base.objects.none(), widget=forms.Select(attrs={'class': 'form-select'}))

    def __init__(self, *args, empresa=None, excluir_base=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Base.objects.filter(empresa=empresa)
        if excluir_base:
            qs = qs.exclude(pk=excluir_base.pk)
        self.fields['base_destino'].queryset = qs
