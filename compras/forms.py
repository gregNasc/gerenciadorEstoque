from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from compras.models import (
    Aquisicao,
    CotacaoFornecedor,
    FornecedorEmpresa,
    ItemAquisicao,
    ItemNotaFiscalAquisicao,
    ItemRemessaCompra,
    RemessaCompra,
)
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

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from estoque.policies.compras import ComprasAccessPolicy

        empresas = ComprasAccessPolicy.empresas(
            user,
            action=ComprasAccessPolicy.CREATE,
        ).order_by('nome')
        self.fields['empresa'].queryset = empresas
        empresa_id = self.data.get('empresa') if self.is_bound else self.initial.get('empresa')
        empresa = empresas.filter(pk=empresa_id).first() if empresa_id else empresas.first()
        if empresa is not None and not self.is_bound:
            self.initial['empresa'] = empresa.pk
        fornecedores_ids = FornecedorEmpresa.objects.filter(
            empresa=empresa,
            status=FornecedorEmpresa.Status.HOMOLOGADO,
            fornecedor__ativo=True,
        ).values('fornecedor_id') if empresa is not None else []
        self.fields['fornecedor'].queryset = FornecedorInsumo.objects.filter(
            pk__in=fornecedores_ids,
            ativo=True,
        ).order_by('nome')
        self.fields['fornecedor'].help_text = _(
            'Somente fornecedores homologados para a empresa selecionada.'
        )
        self.fields['arquivo_danfe_pdf'].label = _('DANFE em PDF')
        self.fields['arquivo_danfe_pdf'].help_text = _(
            'Opcional. PDF válido com até 20 MB; armazenado de forma privada.'
        )
        self.fields['arquivo_danfe_pdf'].widget.attrs['accept'] = 'application/pdf,.pdf'
        self.fields['arquivo_xml_nfe'].label = _('XML da NF-e')
        self.fields['arquivo_xml_nfe'].help_text = _(
            'Opcional. XML válido de NF-e com até 10 MB; armazenado de forma privada.'
        )
        self.fields['arquivo_xml_nfe'].widget.attrs['accept'] = (
            'application/xml,text/xml,.xml'
        )


class FornecedorEmpresaForm(forms.Form):
    empresa = forms.ModelChoiceField(queryset=None, label=_('Empresa'))
    documento_fornecedor = forms.CharField(
        max_length=18,
        label=_('CNPJ do fornecedor'),
        help_text=_(
            'Digite o CNPJ exato. O sistema não exibirá fornecedores de outras empresas.'
        ),
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'inputmode': 'numeric',
            'placeholder': '00.000.000/0000-00',
        }),
    )
    codigo_interno = forms.CharField(
        max_length=80,
        required=False,
        label=_('Código interno'),
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    observacao = forms.CharField(
        required=False,
        label=_('Observação'),
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from estoque.policies.compras import ComprasAccessPolicy

        self.fields['empresa'].queryset = ComprasAccessPolicy.empresas(
            user,
            action=ComprasAccessPolicy.EDIT,
        ).order_by('nome')
        self.fields['empresa'].widget.attrs['class'] = 'form-select'

    def clean_documento_fornecedor(self):
        documento = ''.join(
            caractere for caractere in self.cleaned_data['documento_fornecedor']
            if caractere.isdigit()
        )
        if len(documento) != 14:
            raise forms.ValidationError(_('Informe um CNPJ com 14 dígitos.'))
        fornecedor = FornecedorInsumo.objects.filter(
            documento=documento,
            ativo=True,
        ).first()
        if fornecedor is None:
            raise forms.ValidationError(_(
                'Fornecedor não encontrado ou inativo. Solicite o cadastro canônico ao Superuser.'
            ))
        self.fornecedor_resolvido = fornecedor
        return documento


class CotacaoFornecedorForm(forms.ModelForm):
    class Meta:
        model = CotacaoFornecedor
        fields = [
            'fornecedor_empresa', 'numero_proposta', 'validade_proposta',
            'prazo_entrega_dias', 'frete', 'impostos', 'desconto',
            'condicao_pagamento', 'observacao',
        ]
        labels = {
            'fornecedor_empresa': _('Fornecedor homologado'),
            'numero_proposta': _('Número da proposta'),
            'validade_proposta': _('Validade da proposta'),
            'prazo_entrega_dias': _('Prazo de entrega em dias'),
            'frete': _('Frete'),
            'impostos': _('Impostos'),
            'desconto': _('Desconto'),
            'condicao_pagamento': _('Condição de pagamento'),
            'observacao': _('Observação'),
        }
        widgets = {
            'fornecedor_empresa': forms.Select(attrs={'class': 'form-select'}),
            'numero_proposta': forms.TextInput(attrs={'class': 'form-control'}),
            'validade_proposta': forms.DateInput(attrs={
                'class': 'form-control', 'type': 'date',
            }),
            'prazo_entrega_dias': forms.NumberInput(attrs={
                'class': 'form-control', 'min': 0,
            }),
            'frete': forms.NumberInput(attrs={
                'class': 'form-control', 'min': 0, 'step': '0.01',
            }),
            'impostos': forms.NumberInput(attrs={
                'class': 'form-control', 'min': 0, 'step': '0.01',
            }),
            'desconto': forms.NumberInput(attrs={
                'class': 'form-control', 'min': 0, 'step': '0.01',
            }),
            'condicao_pagamento': forms.TextInput(attrs={'class': 'form-control'}),
            'observacao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, usuario=None, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        from compras.services import FornecedorEmpresaService

        if usuario is None or empresa is None:
            self.fields['fornecedor_empresa'].queryset = FornecedorEmpresa.objects.none()
        else:
            self.fields['fornecedor_empresa'].queryset = (
                FornecedorEmpresaService.homologados(
                    usuario,
                    empresa=empresa,
                ).order_by('fornecedor__nome')
            )


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
    produtos_custodia = forms.ModelMultipleChoiceField(
        queryset=Produto.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_('Equipamentos elegíveis para Custódia pessoal'),
    )
    produtos_individualizaveis = forms.ModelMultipleChoiceField(
        queryset=Produto.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_('Ativos individualizáveis'),
    )
    produtos_com_patrimonio = forms.ModelMultipleChoiceField(
        queryset=Produto.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_('Permitem patrimônio'),
    )
    produtos_patrimonio_obrigatorio = forms.ModelMultipleChoiceField(
        queryset=Produto.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_('Exigem patrimônio'),
    )
    produtos_com_serie = forms.ModelMultipleChoiceField(
        queryset=Produto.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_('Permitem número de série'),
    )
    produtos_serie_obrigatoria = forms.ModelMultipleChoiceField(
        queryset=Produto.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_('Exigem número de série'),
    )
    produtos_com_imei = forms.ModelMultipleChoiceField(
        queryset=Produto.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_('Permitem IMEI'),
    )
    produtos_sick = forms.ModelMultipleChoiceField(
        queryset=Produto.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_('Permitem SICK'),
    )
    produtos_manutencao = forms.ModelMultipleChoiceField(
        queryset=Produto.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_('Permitem manutenção'),
    )
    produtos_transferencia = forms.ModelMultipleChoiceField(
        queryset=Produto.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_('Permitem transferência'),
    )
    produtos_inativacao = forms.ModelMultipleChoiceField(
        queryset=Produto.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_('Permitem inativação'),
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
        self.fields['produtos_custodia'].queryset = produtos
        for nome in (
            'produtos_individualizaveis', 'produtos_com_patrimonio',
            'produtos_patrimonio_obrigatorio', 'produtos_com_serie',
            'produtos_serie_obrigatoria', 'produtos_sick',
            'produtos_com_imei',
            'produtos_manutencao', 'produtos_transferencia',
            'produtos_inativacao',
        ):
            self.fields[nome].queryset = produtos
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
        custodia = set(
            dados.get('produtos_custodia', Produto.objects.none()).values_list(
                'pk', flat=True,
            )
        )
        capacidades = {
            nome: set(dados.get(nome, Produto.objects.none()).values_list('pk', flat=True))
            for nome in (
                'produtos_individualizaveis', 'produtos_com_patrimonio',
                'produtos_patrimonio_obrigatorio', 'produtos_com_serie',
                'produtos_serie_obrigatoria', 'produtos_sick',
                'produtos_com_imei',
                'produtos_manutencao', 'produtos_transferencia',
                'produtos_inativacao',
            )
        }
        if (
            not conectividade <= produtos
            or not chips <= produtos
            or not custodia <= produtos
            or any(not selecionados <= produtos for selecionados in capacidades.values())
        ):
            raise forms.ValidationError(
                'As capacidades só podem ser aplicadas a itens ativos no catálogo.'
            )
        if not capacidades['produtos_patrimonio_obrigatorio'] <= capacidades['produtos_com_patrimonio']:
            raise forms.ValidationError(
                'Todo item que exige patrimônio também deve permitir patrimônio.'
            )
        if not capacidades['produtos_serie_obrigatoria'] <= capacidades['produtos_com_serie']:
            raise forms.ValidationError(
                'Todo item que exige número de série também deve permitir número de série.'
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
    produto = forms.ModelChoiceField(queryset=Produto.objects.none(), required=False)
    item_aquisicao = forms.ModelChoiceField(queryset=ItemAquisicao.objects.none(), required=False)
    item_nfe = forms.ModelChoiceField(
        queryset=ItemNotaFiscalAquisicao.objects.none(),
        required=False,
        label=_('Item correspondente da NF-e'),
    )
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
        self.fields['produto'].queryset = ComprasAccessPolicy.produtos_catalogo(user)
        self.fields['aquisicao'].queryset = Aquisicao.objects.filter(
            empresa__in=empresas
        )
        self.fields['item_aquisicao'].queryset = ItemAquisicao.objects.filter(
            aquisicao__empresa__in=empresas
        )
        self.fields['item_nfe'].queryset = ItemNotaFiscalAquisicao.objects.filter(
            nota_fiscal__aquisicao__empresa__in=empresas,
            status_catalogo=ItemNotaFiscalAquisicao.StatusCatalogo.CONFIRMADO,
        ).select_related('nota_fiscal', 'produto_catalogo', 'insumo_catalogo')

    def clean(self):
        dados = super().clean()
        referencias = [
            dados.get('insumo'), dados.get('equipamento'), dados.get('produto'),
        ]
        if sum(bool(referencia) for referencia in referencias) != 1:
            raise forms.ValidationError(
                'Informe exatamente um insumo, ativo individualizado ou modelo de equipamento.'
            )
        aquisicao = dados.get('aquisicao')
        item_aquisicao = dados.get('item_aquisicao')
        item_nfe = dados.get('item_nfe')
        if item_aquisicao and (
            not aquisicao or item_aquisicao.aquisicao_id != aquisicao.pk
        ):
            self.add_error('item_aquisicao', 'Selecione um item da aquisição informada.')
        if item_nfe and (
            not aquisicao or item_nfe.nota_fiscal.aquisicao_id != aquisicao.pk
        ):
            self.add_error('item_nfe', 'Selecione um item fiscal da aquisição informada.')
        return dados


class IndividualizacaoEquipamentoForm(forms.ModelForm):
    """Identificação física de uma unidade já recebida, sem campos financeiros."""

    class Meta:
        model = Equipamento
        fields = [
            'numero_serie', 'patrimonio', 'imei_1', 'imei_2', 'finalidade',
            'responsavel', 'observacao_operacional', 'foto',
        ]
        widgets = {
            'numero_serie': forms.TextInput(attrs={'class': 'form-control'}),
            'patrimonio': forms.TextInput(attrs={'class': 'form-control'}),
            'imei_1': forms.TextInput(attrs={
                'class': 'form-control', 'inputmode': 'numeric', 'maxlength': 15,
            }),
            'imei_2': forms.TextInput(attrs={
                'class': 'form-control', 'inputmode': 'numeric', 'maxlength': 15,
            }),
            'finalidade': forms.Select(attrs={'class': 'form-select'}),
            'responsavel': forms.TextInput(attrs={'class': 'form-control'}),
            'observacao_operacional': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
            }),
            'foto': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, item_remessa: ItemRemessaCompra, **kwargs):
        super().__init__(*args, **kwargs)
        self.item_remessa = item_remessa
        from estoque.services.ativo_capacidade_service import AtivoCapacidadeService

        self.regras = AtivoCapacidadeService.identificadores(
            empresa=item_remessa.remessa.empresa,
            produto=item_remessa.produto,
        )
        self.fields['numero_serie'].required = self.regras['serie_obrigatoria']
        self.fields['patrimonio'].required = self.regras['patrimonio_obrigatorio']
        self.fields['imei_1'].required = False
        self.fields['imei_2'].required = False
        self.fields['imei_1'].label = _('IMEI 1 (opcional)')
        self.fields['imei_2'].label = _('IMEI 2 (opcional)')

    def clean_numero_serie(self):
        serie = (self.cleaned_data.get('numero_serie') or '').strip().upper() or None
        if serie and Equipamento.objects.filter(numero_serie=serie).exists():
            raise forms.ValidationError(_('Número de série já cadastrado.'))
        return serie

    def clean_patrimonio(self):
        patrimonio = (self.cleaned_data.get('patrimonio') or '').strip().upper() or None
        if not patrimonio:
            return None
        if Equipamento.objects.filter(patrimonio=patrimonio).exists():
            raise forms.ValidationError(_('Patrimônio já cadastrado.'))
        from insumos.models import AtivoInsumoIndividualizado
        if AtivoInsumoIndividualizado.objects.filter(
            patrimonio__iexact=patrimonio,
        ).exists():
            raise forms.ValidationError(
                _('Este patrimônio já pertence a um insumo individualizado.')
            )
        return patrimonio

    def _clean_imei(self, campo):
        imei = (self.cleaned_data.get(campo) or '').strip() or None
        if not imei:
            return None
        if not imei.isdigit() or len(imei) != 15:
            raise forms.ValidationError(_('Informe exatamente 15 dígitos numéricos.'))
        if Equipamento.objects.filter(Q(imei_1=imei) | Q(imei_2=imei)).exists():
            raise forms.ValidationError(_('IMEI já cadastrado.'))
        return imei

    def clean_imei_1(self):
        return self._clean_imei('imei_1')

    def clean_imei_2(self):
        return self._clean_imei('imei_2')

    def clean(self):
        dados = super().clean()
        from estoque.services.ativo_capacidade_service import AtivoCapacidadeService

        serie, patrimonio, regras, erros = AtivoCapacidadeService.validar_identificadores(
            empresa=self.item_remessa.remessa.empresa,
            produto=self.item_remessa.produto,
            numero_serie=dados.get('numero_serie'),
            patrimonio=dados.get('patrimonio'),
        )
        dados['numero_serie'] = serie
        dados['patrimonio'] = patrimonio
        for campo, mensagem in erros.items():
            self.add_error(campo, mensagem)
        imei_1 = dados.get('imei_1')
        imei_2 = dados.get('imei_2')
        if not regras['possui_imei'] and (imei_1 or imei_2):
            self.add_error('imei_1', _('Este modelo não utiliza IMEI.'))
        if imei_1 and imei_2 and imei_1 == imei_2:
            self.add_error('imei_2', _('O IMEI 2 deve ser diferente do IMEI 1.'))
        return dados
