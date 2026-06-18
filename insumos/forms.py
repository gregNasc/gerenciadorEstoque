from django import forms
from estoque.models import Base
from insumos.models import Insumo, CategoriaInsumo

class InsumoForm(forms.ModelForm):
    base = forms.ModelChoiceField(
        queryset=Base.objects.all(),
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Insumo
        fields = [
            'base',
            'descricao',
            'categoria',
            'unidade_medida',
            'tipo_controle',
            'estoque_minimo',
            'estoque_maximo',
            'ativo',
        ]

        widgets = {
            'descricao': forms.TextInput(
                attrs={'class': 'form-control'}
            ),
            'categoria': forms.Select(
                attrs={'class': 'form-select'}
            ),
            'unidade_medida': forms.TextInput(
                attrs={'class': 'form-control'}
            ),
            'tipo_controle': forms.Select(
                attrs={'class': 'form-select'}
            ),
            'valor_medio': forms.NumberInput(
                attrs={'class': 'form-control'}
            ),
            'estoque_minimo': forms.NumberInput(
                attrs={'class': 'form-control'}
            ),
            'estoque_maximo': forms.NumberInput(
                attrs={'class': 'form-control'}
            ),
            'ativo': forms.CheckboxInput(
                attrs={'class': 'form-check-input'}
            ),
        }

class CadastroInsumoForm(forms.Form):

    base = forms.ModelChoiceField(queryset=Base.objects.all(), widget=forms.Select(attrs={'class': 'form-select'}))
    categoria = forms.ModelChoiceField(queryset=CategoriaInsumo.objects.all().order_by('nome'), widget=forms.Select(attrs={'class': 'form-select'}))
    insumo = forms.ModelChoiceField(queryset=Insumo.objects.none(), widget=forms.Select(attrs={'class': 'form-select'}))
    quantidade = forms.DecimalField(min_value=0.01, decimal_places=2, max_digits=10, widget=forms.NumberInput(attrs={'class': 'form-control'}))

    def __init__(self, *args, user=None, **kwargs):

        super().__init__(*args, **kwargs)

        if user:
            self.fields['base'].queryset = user.perfil.regionais.all()

        # GET
        if self.data.get('categoria'):

            try:
                categoria_id = int(self.data.get('categoria'))

                self.fields['insumo'].queryset = (
                    Insumo.objects
                    .filter(
                        categoria_id=categoria_id,
                        ativo=True
                    )
                    .order_by('descricao')
                )

            except (TypeError, ValueError):
                pass