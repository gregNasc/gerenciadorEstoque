from django import forms
from django.db.models import Q
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

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from estoque.policies.compras import ComprasAccessPolicy

        empresas = ComprasAccessPolicy.empresas(
            user,
            action=ComprasAccessPolicy.CREATE,
        )
        empresa_id = self.data.get('empresa') if self.is_bound else None
        empresa = (
            empresas.filter(pk=empresa_id).first()
            if empresa_id and str(empresa_id).isdigit()
            else empresas.first()
        )
        self.fields['produto'].queryset = ComprasAccessPolicy.produtos_catalogo(
            user,
            empresa=empresa,
        )


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


class CatalogoEmpresaForm(forms.Form):
    empresa = forms.ModelChoiceField(queryset=None, label='Empresa')
    produtos = forms.ModelMultipleChoiceField(
        queryset=Produto.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Equipamentos disponíveis',
    )
    produtos_conectividade_movel = forms.ModelMultipleChoiceField(
        queryset=Produto.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Equipamentos que aceitam chip / linha móvel',
    )
    produtos_chip_independente = forms.ModelMultipleChoiceField(
        queryset=Produto.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Produtos que representam chip como ativo independente',
    )

    def __init__(self, *args, user=None, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        from compras.models import (
            CapacidadeCatalogoProdutoEmpresa,
            CatalogoProdutoEmpresa,
        )
        from estoque.policies.compras import ComprasAccessPolicy
        from estoque.policies.linhas_moveis import LinhasMoveisAccessPolicy

        self.pode_configurar_linhas_moveis = LinhasMoveisAccessPolicy.permite(
            user,
            LinhasMoveisAccessPolicy.MANAGE,
        )

        empresas = ComprasAccessPolicy.empresas(
            user,
            action=ComprasAccessPolicy.ADMIN,
            resource=ComprasAccessPolicy.CATALOGO,
        ).order_by('nome')
        self.fields['empresa'].queryset = empresas
        produtos = Produto.objects.filter(ativo=True)
        if not (user and user.is_superuser):
            produtos = produtos.filter(
                Q(empresa_catalogo_origem__in=empresas)
                | Q(
                    catalogos_empresa__empresa=empresa,
                    catalogos_empresa__ativo=True,
                ),
            ).distinct()
        if empresa is not None and not self.pode_configurar_linhas_moveis:
            produtos_chip = CatalogoProdutoEmpresa.objects.filter(
                empresa=empresa,
                ativo=True,
                capacidades__codigo=(
                    CapacidadeCatalogoProdutoEmpresa.ATIVO_LINHA_MOVEL
                ),
                capacidades__ativa=True,
            ).values('produto_id')
            produtos = produtos.exclude(pk__in=produtos_chip)
        produtos = produtos.order_by('categoria', 'descricao')
        self.fields['produtos'].queryset = produtos
        if self.pode_configurar_linhas_moveis:
            self.fields['produtos_conectividade_movel'].queryset = produtos
            self.fields['produtos_chip_independente'].queryset = produtos
        else:
            self.fields.pop('produtos_conectividade_movel')
            self.fields.pop('produtos_chip_independente')

    def clean(self):
        dados = super().clean()
        produtos = set(
            dados.get('produtos', Produto.objects.none()).values_list('pk', flat=True)
        )
        conectividade = set(
            dados.get('produtos_conectividade_movel', Produto.objects.none()).values_list(
                'pk', flat=True,
            )
        )
        chips = set(
            dados.get('produtos_chip_independente', Produto.objects.none()).values_list(
                'pk', flat=True,
            )
        )
        if not conectividade <= produtos or not chips <= produtos:
            raise forms.ValidationError(
                'As capacidades móveis só podem ser aplicadas a itens ativos no catálogo.'
            )
        sobreposicao = conectividade & chips
        if sobreposicao:
            raise forms.ValidationError(
                'Um produto não pode ser simultaneamente equipamento vinculável e chip independente.'
            )
        return dados


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
        empresas = ComprasAccessPolicy.empresas(
            user,
            action=ComprasAccessPolicy.CREATE,
        )
        bases = ComprasAccessPolicy.bases(
            user,
            action=ComprasAccessPolicy.CREATE,
        )
        self.fields['empresa'].queryset = empresas
        self.fields['base_origem'].queryset = bases
        self.fields['base_destino'].queryset = bases
        self.fields['equipamento'].queryset = Equipamento.objects.filter(
            regional__in=bases
        )
        self.fields['aquisicao'].queryset = Aquisicao.objects.filter(
            empresa__in=empresas
        )
        self.fields['item_aquisicao'].queryset = ItemAquisicao.objects.filter(
            aquisicao__empresa__in=empresas
        )

    def clean(self):
        dados = super().clean()
        if bool(dados.get('insumo')) == bool(dados.get('equipamento')):
            raise forms.ValidationError('Informe exatamente um insumo ou equipamento.')
        return dados
