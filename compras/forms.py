from django import forms
from django.utils.translation import gettext_lazy as _

from compras.models import Aquisicao, ItemAquisicao, RemessaCompra
from estoque.models import Base, Equipamento, Produto
from insumos.models import FornecedorInsumo, Insumo


class AquisicaoForm(forms.ModelForm):
    class Meta:
        model = Aquisicao
        fields = [
            'empresa', 'fornecedor', 'numero_documento', 'chave_nfe',
            'arquivo_danfe_pdf', 'arquivo_xml_nfe', 'numero_pedido_compra',
            'centro_custo', 'data_compra', 'observacao',
        ]
        widgets = {'data_compra': forms.DateInput(attrs={'type': 'date'})}


class ItemAquisicaoForm(forms.Form):
    tipo_item = forms.ChoiceField(choices=ItemAquisicao.Tipo.choices)
    produto = forms.ModelChoiceField(queryset=Produto.objects.filter(ativo=True), required=False)
    insumo = forms.ModelChoiceField(queryset=Insumo.objects.filter(ativo=True), required=False)
    quantidade = forms.DecimalField(min_value=0.01, decimal_places=2)
    valor_unitario = forms.DecimalField(min_value=0, decimal_places=4)
    desconto = forms.DecimalField(min_value=0, decimal_places=2, initial=0)
    frete = forms.DecimalField(min_value=0, decimal_places=2, initial=0)
    impostos = forms.DecimalField(min_value=0, decimal_places=2, initial=0)


class ImportacaoPrecificacaoForm(forms.Form):
    arquivo = forms.FileField(
        help_text=_('Planilha XLSX gerada pelo template de precificação.')
    )

    def clean_arquivo(self):
        arquivo = self.cleaned_data['arquivo']
        if not arquivo.name.lower().endswith('.xlsx'):
            raise forms.ValidationError(_('Envie uma planilha no formato XLSX.'))
        if arquivo.size > 10 * 1024 * 1024:
            raise forms.ValidationError(_('A planilha não pode ultrapassar 10 MB.'))
        return arquivo


class RemessaForm(forms.Form):
    empresa = forms.ModelChoiceField(queryset=None)
    fluxo = forms.ChoiceField(choices=RemessaCompra.Fluxo.choices)
    aquisicao = forms.ModelChoiceField(queryset=Aquisicao.objects.none(), required=False)
    base_origem = forms.ModelChoiceField(queryset=Base.objects.none(), required=False)
    base_destino = forms.ModelChoiceField(queryset=Base.objects.none())
    insumo = forms.ModelChoiceField(queryset=Insumo.objects.filter(ativo=True), required=False)
    equipamento = forms.ModelChoiceField(queryset=Equipamento.objects.all(), required=False)
    item_aquisicao = forms.ModelChoiceField(queryset=ItemAquisicao.objects.none(), required=False)
    quantidade = forms.DecimalField(min_value=0.01, decimal_places=2, initial=1)
    custo_unitario = forms.DecimalField(min_value=0, decimal_places=4, initial=0)
    previsao_chegada = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    observacao = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 3}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from estoque.policies.compras import ComprasAccessPolicy
        empresas = ComprasAccessPolicy.empresas(user)
        bases = ComprasAccessPolicy.bases(user)
        self.fields['empresa'].queryset = empresas
        self.fields['base_origem'].queryset = bases
        self.fields['base_destino'].queryset = bases
        self.fields['aquisicao'].queryset = Aquisicao.objects.filter(empresa__in=empresas)
        self.fields['item_aquisicao'].queryset = ItemAquisicao.objects.filter(aquisicao__empresa__in=empresas)

    def clean(self):
        dados = super().clean()
        if bool(dados.get('insumo')) == bool(dados.get('equipamento')):
            raise forms.ValidationError('Informe exatamente um insumo ou equipamento.')
        return dados
