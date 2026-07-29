from django import forms
from django.utils.translation import gettext_lazy as _
from estoque.models import Base
from insumos.models import (
    CategoriaInsumo,
    FornecedorInsumo,
    Insumo,
    Inventario,
    PrecoFornecedorInsumo,
    SolicitacaoInsumo,
)
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
                attrs={
                    'class': 'form-control',
                    'min': '0',
                    'max': '10',
                    'step': '0.01',
                }
            ),
            'estoque_maximo': forms.NumberInput(
                attrs={'class': 'form-control'}
            ),
            'ativo': forms.CheckboxInput(
                attrs={'class': 'form-check-input'}
            ),
        }


class FornecedorInsumoForm(forms.ModelForm):
    documento = forms.CharField(
        label=_('CNPJ'),
        max_length=18,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'inputmode': 'numeric',
            'placeholder': '00.000.000/0000-00',
        }),
    )

    def clean_documento(self):
        documento = ''.join(ch for ch in self.cleaned_data['documento'] if ch.isdigit())
        if len(documento) != 14:
            raise forms.ValidationError(_('Informe um CNPJ com 14 dígitos.'))
        return documento

    class Meta:
        model = FornecedorInsumo
        fields = [
            'nome', 'documento', 'site', 'contato', 'email', 'telefone',
            'prazo_entrega_dias', 'observacao', 'ativo',
        ]
        labels = {
            'nome': _('Nome'),
            'documento': _('CNPJ'),
            'site': _('Site'),
            'contato': _('Contato'),
            'email': _('E-mail'),
            'telefone': _('Telefone'),
            'prazo_entrega_dias': _('Prazo de entrega em dias'),
            'observacao': _('Observação'),
            'ativo': _('Ativo'),
        }
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'documento': forms.TextInput(attrs={'class': 'form-control'}),
            'site': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://fornecedor.com.br/',
            }),
            'contato': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'telefone': forms.TextInput(attrs={'class': 'form-control'}),
            'prazo_entrega_dias': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'observacao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class PrecoFornecedorInsumoForm(forms.ModelForm):
    aplicar_como_custo = forms.BooleanField(
        required=False,
        initial=True,
        label=_('Usar como custo atual do insumo'),
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    class Meta:
        model = PrecoFornecedorInsumo
        fields = [
            'insumo', 'fornecedor', 'valor_unitario', 'vigente_desde',
            'vigente_ate', 'ativo', 'observacao',
        ]
        labels = {
            'insumo': _('Insumo'),
            'fornecedor': _('Fornecedor'),
            'valor_unitario': _('Preço unitário'),
            'vigente_desde': _('Vigente desde'),
            'vigente_ate': _('Vigente até'),
            'ativo': _('Ativo'),
            'observacao': _('Observação'),
        }
        widgets = {
            'insumo': forms.Select(attrs={'class': 'form-select'}),
            'fornecedor': forms.Select(attrs={'class': 'form-select'}),
            'valor_unitario': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0.0001', 'step': '0.0001',
            }),
            'vigente_desde': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'vigente_ate': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'observacao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class SolicitacaoInsumoForm(forms.ModelForm):
    class Meta:
        model = SolicitacaoInsumo
        fields = ['base', 'prioridade', 'justificativa']
        labels = {
            'base': _('Base solicitante'),
            'prioridade': _('Prioridade'),
            'justificativa': _('Justificativa'),
        }
        widgets = {
            'base': forms.Select(attrs={'class': 'form-select'}),
            'prioridade': forms.Select(attrs={'class': 'form-select'}),
            'justificativa': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and user.perfil.is_admin:
            self.fields['base'].queryset = Base.objects.order_by('nome')
        elif user:
            self.fields['base'].queryset = user.perfil.regionais.order_by('nome')
        else:
            self.fields['base'].queryset = Base.objects.none()

class CadastroInsumoForm(forms.Form):

    base = forms.ModelChoiceField(queryset=Base.objects.all(), widget=forms.Select(attrs={'class': 'form-select'}))
    categoria = forms.ModelChoiceField(queryset=CategoriaInsumo.objects.all().order_by('nome'), widget=forms.Select(attrs={'class': 'form-select'}))
    insumo = forms.ModelChoiceField(queryset=Insumo.objects.none(), widget=forms.Select(attrs={'class': 'form-select'}))
    quantidade = forms.DecimalField(min_value=1, decimal_places=2, max_digits=10, widget=forms.NumberInput(attrs={'class': 'form-control'}))

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
    EXTERNAL_PLANNING_FIELDS = {
        'cliente', 'loja', 'base', 'data_inicio', 'inicio_previsto',
        'endereco', 'bairro', 'cidade', 'tipo', 'pessoas', 'observacao',
        'ponto_encontro', 'horario_inicio', 'equipe_plan', 'previsao_pecas',
        'cnpj', 'cep',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance or not self.instance.pk:
            return
        from integracao.models import InventoryPlanningEventBinding

        if not InventoryPlanningEventBinding.objects.filter(inventory=self.instance).exists():
            return
        for field_name in self.EXTERNAL_PLANNING_FIELDS:
            field = self.fields.get(field_name)
            if field:
                field.disabled = True
                field.help_text = 'Campo oficial sincronizado pela Inventory Planning API.'

    class Meta:
        model = Inventario
        fields = [
            'cliente', 'loja', 'base', 'data_inicio', 'data_fim', 'status',
            'inicio_previsto', 'fim_previsto', 'inicio_real', 'fim_real',
            'inicio_contagem', 'fim_contagem',
            'endereco', 'bairro', 'cidade',
            'tipo', 'pessoas', 'total_pecas', 'custo_hora_pessoa',
            'observacao', 'lider', 'ponto_encontro',
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
            'inicio_previsto': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={'type': 'datetime-local', 'class': 'form-control'},
            ),
            'fim_previsto': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={'type': 'datetime-local', 'class': 'form-control'},
            ),
            'inicio_real': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={'type': 'datetime-local', 'class': 'form-control'},
            ),
            'fim_real': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={'type': 'datetime-local', 'class': 'form-control'},
            ),
            'inicio_contagem': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={'type': 'datetime-local', 'class': 'form-control'},
            ),
            'fim_contagem': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={'type': 'datetime-local', 'class': 'form-control'},
            ),
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
            'inicio_previsto': 'Início previsto',
            'fim_previsto': 'Fim previsto',
            'inicio_real': 'Início real',
            'fim_real': 'Fim real',
            'inicio_contagem': 'Início da contagem',
            'fim_contagem': 'Fim da contagem',
            'total_pecas': 'Total de peças contadas',
            'custo_hora_pessoa': 'Custo por pessoa/hora',
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
