from django import forms
from estoque.models import Base
from insumos.models import Insumo, CategoriaInsumo, Inventario
from django_select2.forms import Select2Widget

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

class FiltroEstoqueInsumoForm(forms.Form):

    categoria = forms.ModelChoiceField(
        queryset=CategoriaInsumo.objects.all().order_by('nome'),
        required=False,
        empty_label='Todas as categorias',
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )

    insumo = forms.ModelChoiceField(
        queryset=Insumo.objects.all().order_by('descricao'),
        required=False,
        empty_label='Todos os insumos',
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        categoria_id = self.data.get('categoria')

        if categoria_id:
            self.fields['insumo'].queryset = (
                Insumo.objects
                .filter(categoria_id=categoria_id)
                .order_by('descricao')
            )
        else:
            self.fields['insumo'].queryset = (
                Insumo.objects
                .order_by('descricao')
            )

class InventarioForm(forms.ModelForm):
    class Meta:
        model = Inventario
        fields = [
            'cliente', 'loja', 'base', 'data_inicio', 'data_fim', 'status',
            'endereco', 'bairro', 'cidade',
            'tipo', 'pessoas', 'observacao', 'lider', 'ponto_encontro',
            'horario_ponto', 'horario_inicio', 'tipo_visita', 'responsavel_visita',
            'data_visita', 'horario_visita', 'relatorio_visita', 'prep',
            'historico_equipe', 'historico_pecas', 'historico_satisfacao',
            'historico_preparacao', 'historico_lider', 'historico_data',
            'equipe_plan', 'previsao_pecas', 'prod_media', 'bid', 'cnpj', 'cep',
            'envio_escala', 'chave',
        ]
        widgets = {
            'cliente': Select2Widget(attrs={'class': 'form-control'}),
            'base': Select2Widget(attrs={'class': 'form-control'}),
            'data_inicio': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'data_fim': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'data_visita': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'historico_data': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'envio_escala': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'horario_ponto': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'horario_inicio': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'horario_visita': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'observacao': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }
        labels = {
            'tipo': 'Tipo',
            'pessoas': 'Pessoas',
            'observacao': 'Observação',
            'lider': 'Líder',
            'ponto_encontro': 'Ponto de Encontro',
            'horario_ponto': 'Horário do Ponto',
            'horario_inicio': 'Horário de Início',
            'tipo_visita': 'Tipo da Visita',
            'responsavel_visita': 'Responsável pela Visita',
            'data_visita': 'Data da Visita',
            'horario_visita': 'Horário da Visita',
            'relatorio_visita': 'Relatório de Visita',
            'prep': 'Preparação',
            'historico_equipe': 'Histórico Equipe',
            'historico_pecas': 'Histórico Peças',
            'historico_satisfacao': 'Histórico Satisfação',
            'historico_preparacao': 'Histórico Preparação',
            'historico_lider': 'Histórico Líder',
            'historico_data': 'Histórico Data',
            'equipe_plan': 'Equipe Planejada',
            'previsao_pecas': 'Previsão de Peças',
            'prod_media': 'Produtividade Média',
            'bid': 'BID',
            'cnpj': 'CNPJ',
            'cep': 'CEP',
            'envio_escala': 'Envio da Escala',
            'chave': 'Chave',
        }