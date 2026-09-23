from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import (
    Base,
    CategoriaEquipamentoEmpresa,
    DeclaracaoCorreios,
    DeclaracaoCorreiosItem,
    Empresa,
    Equipamento,
    Produto,
    Sick,
    Transferencia,
)
from django.utils.translation import gettext_lazy as _
from insumos.models import FornecedorInsumo
from estoque.security import secure_base_queryset


class DeclaracaoCorreiosForm(forms.ModelForm):
    class Meta:
        model = DeclaracaoCorreios
        fields = [
            'quantidade_volumes',
            'valor_total_declarado',
            'peso_total_kg',
            'observacoes',
        ]
        labels = {
            'quantidade_volumes': _('Quantidade de volumes'),
            'valor_total_declarado': _('Valor total declarado'),
            'peso_total_kg': _('Peso total (kg)'),
            'observacoes': _('Observações'),
        }
        widgets = {
            'quantidade_volumes': forms.NumberInput(attrs={'min': 1, 'class': 'form-control'}),
            'valor_total_declarado': forms.NumberInput(attrs={'min': 0, 'step': '0.01', 'class': 'form-control'}),
            'peso_total_kg': forms.NumberInput(attrs={'min': 0, 'step': '0.001', 'class': 'form-control'}),
            'observacoes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

class DeclaracaoEnderecoForm(forms.Form):
    nome_destinatario = forms.CharField(label=_('Nome'), max_length=150)
    logradouro = forms.CharField(label=_('Logradouro'), max_length=180)
    numero = forms.CharField(label=_('Número'), max_length=30)
    complemento = forms.CharField(label=_('Complemento'), max_length=100, required=False)
    bairro = forms.CharField(label=_('Bairro'), max_length=100)
    cidade = forms.CharField(label=_('Cidade'), max_length=100)
    uf = forms.CharField(label=_('UF'), max_length=2)
    cep = forms.CharField(label=_('CEP'), max_length=9)
    documento = forms.CharField(label=_('CPF/CNPJ/Documento estrangeiro'), max_length=30, required=False)
    telefone = forms.CharField(label=_('Telefone'), max_length=20, required=False)
    responsavel = forms.CharField(label=_('Responsável'), max_length=150, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault('class', 'form-control')

DeclaracaoCorreiosItemFormSet = forms.inlineformset_factory(
    DeclaracaoCorreios,
    DeclaracaoCorreiosItem,
    fields=['descricao', 'quantidade', 'valor_unitario', 'patrimonio', 'numero_serie', 'ordem'],
    extra=0,
    can_delete=False,
    widgets={
        'descricao': forms.TextInput(attrs={'class': 'form-control'}),
        'quantidade': forms.NumberInput(attrs={'min': 1, 'class': 'form-control'}),
        'valor_unitario': forms.NumberInput(attrs={'min': 0, 'step': '0.01', 'class': 'form-control'}),
        'patrimonio': forms.TextInput(attrs={'class': 'form-control'}),
        'numero_serie': forms.TextInput(attrs={'class': 'form-control'}),
        'ordem': forms.HiddenInput(),
    },
)

# ================= PRODUTO =================
class ProdutoForm(forms.ModelForm):
    categoria = forms.CharField(
        label=_('Categoria'),
        max_length=100,
        help_text=_(
            'Informe uma categoria adequada ao uso da empresa. '
            'Ela ficará disponível quando este item estiver habilitado no catálogo.'
        ),
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'list': 'categorias-equipamento-sugeridas',
            'placeholder': _('Informe uma categoria da empresa'),
        }),
    )
    empresa_catalogo = forms.ModelChoiceField(
        label=_('Empresa do catálogo'),
        queryset=Empresa.objects.none(),
        help_text=_('A nova ficha técnica ficará habilitada nesta empresa.'),
    )
    preco_referencia_inicial = forms.DecimalField(
        label=_('Preço de referência'),
        required=False,
        min_value=0,
        max_digits=14,
        decimal_places=4,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': '0.01'}),
        help_text=_('Opcional. Itens futuros deste produto reutilizarão este valor.'),
    )
    preco_origem = forms.ChoiceField(
        label=_('Origem do preço'),
        required=False,
        choices=Produto.OrigemPreco.choices,
        initial=Produto.OrigemPreco.INFORMADO_COMPRAS,
    )
    preco_fonte = forms.CharField(
        label=_('Fonte'), required=False, max_length=255,
        help_text=_('Documento, pesquisa ou referência utilizada.'),
    )
    preco_fornecedor = forms.ModelChoiceField(
        label=_('Fornecedor'), required=False, queryset=FornecedorInsumo.objects.none(),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from estoque.policies.compras import ComprasAccessPolicy

        self.user = user
        empresas_catalogo = ComprasAccessPolicy.empresas(
            user,
            action=ComprasAccessPolicy.ADMIN,
            resource=ComprasAccessPolicy.CATALOGO,
        ).order_by('nome')
        self.fields['empresa_catalogo'].queryset = empresas_catalogo
        perfil = getattr(user, 'perfil', None)
        if perfil and perfil.empresa_id and empresas_catalogo.filter(
            pk=perfil.empresa_id
        ).exists():
            self.fields['empresa_catalogo'].initial = perfil.empresa_id
        empresa_id = self.data.get('empresa_catalogo') if self.is_bound else None
        if not empresa_id:
            empresa_id = self.fields['empresa_catalogo'].initial
        empresa_sugerida = (
            empresas_catalogo.filter(pk=empresa_id).first()
            if empresa_id and str(empresa_id).isdigit()
            else None
        )
        from estoque.services.tenant_catalog_service import TenantCatalogService
        self.categorias_sugeridas = TenantCatalogService.category_names(
            user,
            company=empresa_sugerida,
        )
        self.fields['preco_fornecedor'].queryset = FornecedorInsumo.objects.filter(
            ativo=True
        ).order_by('nome')
        pode_definir = bool(
            user
            and not ComprasAccessPolicy.restrito(user)
            and (
                ComprasAccessPolicy.pode_definir_preco_produto(user)
            )
        )
        if not pode_definir:
            for nome in (
                'preco_referencia_inicial', 'preco_origem',
                'preco_fonte', 'preco_fornecedor',
            ):
                self.fields.pop(nome, None)

    def clean(self):
        dados = super().clean()
        empresa_catalogo = dados.get('empresa_catalogo')
        if empresa_catalogo is not None:
            self.instance.empresa_catalogo_origem = empresa_catalogo
        if 'preco_referencia_inicial' in self.fields and dados.get('preco_referencia_inicial') is not None:
            dados['preco_origem'] = (
                dados.get('preco_origem') or Produto.OrigemPreco.INFORMADO_COMPRAS
            )
        return dados

    class Meta:
        model = Produto
        fields = [
            'empresa_catalogo', 'codigo', 'descricao', 'nome_resumido', 'fabricante', 'modelo',
            'sku_fabricante', 'categoria', 'subcategoria', 'unidade_medida',
            'quantidade_embalagem', 'especificacoes_tecnicas', 'ativo',
        ]
        widgets = {
            'codigo': forms.TextInput(attrs={'class': 'form-control'}),
            'descricao': forms.TextInput(attrs={'class': 'form-control'}),
            'fabricante': forms.TextInput(attrs={'class': 'form-control'}),
            'modelo': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_codigo(self):
        codigo = self.cleaned_data['codigo'].strip().upper()
        empresa = self.cleaned_data.get('empresa_catalogo')
        if empresa is None:
            empresa = self.instance.empresa_catalogo_origem
        if (
            empresa is not None
            and Produto.objects.filter(
                empresa_catalogo_origem=empresa,
                codigo=codigo,
            ).exclude(pk=self.instance.pk).exists()
        ):
            raise ValidationError(
                "Já existe um produto com esse código nesta empresa."
            )
        return codigo

    def clean_categoria(self):
        categoria = self.cleaned_data['categoria'].strip()
        if not categoria:
            raise ValidationError(_('Informe a categoria do equipamento.'))
        empresa = self.cleaned_data.get('empresa_catalogo')
        configuracao = CategoriaEquipamentoEmpresa.objects.filter(
            empresa=empresa,
            nome__iexact=categoria,
        ).first() if empresa is not None else None
        if configuracao is not None and not configuracao.ativo:
            raise ValidationError(
                _('A categoria está desativada para esta empresa.')
            )
        return categoria

# ================= EQUIPAMENTO =================
class EquipamentoForm(forms.ModelForm):

    categoria = forms.ChoiceField(
        choices=[('', _('Selecione'))],
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    class Meta:
        model = Equipamento
        fields = [
            'categoria',
            'produto',
            'numero_serie',
            'patrimonio',
            'regional',
            'finalidade',
            'responsavel',
            'foto',
        ]

        widgets = {
            'produto': forms.Select(attrs={'class': 'form-control'}),
            'numero_serie': forms.TextInput(attrs={'class': 'form-control'}),
            'patrimonio': forms.TextInput(attrs={'class': 'form-control'}),
            'regional': forms.Select(attrs={'class': 'form-control'}),
            'finalidade': forms.Select(attrs={'class': 'form-control'}),
            'responsavel': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, user=None, base_selecionada=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.base_selecionada = base_selecionada
        from estoque.policies.compras import ComprasAccessPolicy

        base_catalogo = base_selecionada
        regional_id = self.data.get('regional') if self.is_bound else None
        if base_catalogo is None and regional_id and str(regional_id).isdigit():
            base_catalogo = secure_base_queryset(
                Base.objects.select_related('empresa'),
                user,
                resource='EQUIPAMENTOS',
                action='CRIAR',
            ).filter(pk=regional_id).first()
        if base_catalogo is None and self.instance.pk:
            base_catalogo = self.instance.regional

        produtos_permitidos = ComprasAccessPolicy.produtos_catalogo(
            user,
            empresa=base_catalogo.empresa if base_catalogo else None,
        )
        from estoque.services.tenant_catalog_service import TenantCatalogService
        categorias = TenantCatalogService.category_names(
            user,
            company=base_catalogo.empresa if base_catalogo else None,
        )
        self.fields['categoria'].choices = [('', _('Selecione'))] + [
            (categoria, categoria) for categoria in categorias
        ]
        categoria = self.data.get('categoria') if self.is_bound else None
        if not categoria and self.instance.pk and self.instance.produto_id:
            categoria = self.instance.produto.categoria
        self.fields['produto'].queryset = (
            produtos_permitidos.filter(categoria=categoria).order_by('descricao')
            if categoria
            else Produto.objects.none()
        )

        if user and not user.is_superuser:
            perfil = getattr(user, 'perfil', None)

            if perfil:
                from estoque.policies.compras import ComprasAccessPolicy
                if perfil.is_admin:
                    self.fields['regional'].queryset = secure_base_queryset(
                        Base.objects.all(),
                        user,
                        action='CRIAR',
                    )
                elif perfil.is_compras_insumos:
                    self.fields['regional'].queryset = secure_base_queryset(
                        Base.objects.all(),
                        user,
                        action='CRIAR',
                    )
                else:
                    regionais = perfil.regionais.all()

                    self.fields['regional'].queryset = regionais

                    if regionais.count() == 1:
                        self.fields['regional'].initial = regionais.first()

        if base_selecionada is not None:
            self.fields['regional'].queryset = Base.objects.filter(pk=base_selecionada.pk)
            self.fields['regional'].initial = base_selecionada
            self.fields['regional'].disabled = True

    def clean_numero_serie(self):
        serie = self.cleaned_data['numero_serie'].strip().upper()
        if Equipamento.objects.filter(numero_serie=serie).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Número de série já cadastrado.")
        return serie

    def clean_patrimonio(self):
        patrimonio = self.cleaned_data['patrimonio'].strip().upper()
        if Equipamento.objects.filter(patrimonio=patrimonio).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Patrimônio já cadastrado.")
        return patrimonio

    def clean_regional(self):
        regional = self.cleaned_data.get('regional')
        if regional is None:
            raise ValidationError("Informe uma base válida.")

        perfil = getattr(self.user, 'perfil', None)
        if not perfil:
            raise ValidationError("Usuário sem perfil de acesso.")
        if not secure_base_queryset(
            Base.objects.filter(pk=regional.pk),
            self.user,
            action='CRIAR',
        ).exists():
            raise ValidationError("Você não possui acesso a esta base.")
        if self.base_selecionada and regional.pk != self.base_selecionada.pk:
            raise ValidationError("A base informada diverge do contexto selecionado.")
        return regional

    def clean(self):
        dados = super().clean()
        regional = dados.get('regional')
        produto = dados.get('produto')
        categoria = dados.get('categoria')
        if produto and categoria and produto.categoria != categoria:
            self.add_error('produto', 'O equipamento não pertence à categoria selecionada.')
        if regional and produto:
            from estoque.policies.compras import ComprasAccessPolicy

            if not ComprasAccessPolicy.produtos_catalogo(
                self.user,
                empresa=regional.empresa,
            ).filter(pk=produto.pk).exists():
                self.add_error(
                    'produto',
                    'Este equipamento não está habilitado no catálogo da empresa.',
                )
        return dados

# ================= TRANSFERÊNCIA =================
class TransferenciaForm(forms.ModelForm):
    class Meta:
        model = Transferencia
        fields = ['regional_destino']
        widgets = {
            'regional_destino': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, equipamento=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        if not equipamento:
            raise ValueError("Equipamento obrigatório para transferência")

        self.equipamento = equipamento
        self.user = user

        self.fields['regional_destino'].queryset = Base.objects.exclude(
            id=equipamento.regional_id
        )

    def clean(self):
        cleaned = super().clean()
        destino = cleaned.get('regional_destino')

        if self.equipamento.status != 'ATIVO':
            raise ValidationError("Equipamento não disponível para transferência.")

        if destino and destino == self.equipamento.regional:
            raise ValidationError("Destino não pode ser igual à origem.")

        if Transferencia.objects.filter(
            equipamento=self.equipamento,
            status__in=['SOLICITADO', 'PENDENTE', 'ENVIADO']
        ).exists():
            raise ValidationError("Já existe uma transferência pendente.")

        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)

        obj.equipamento = self.equipamento
        obj.regional_origem = self.equipamento.regional
        obj.solicitado_por = self.user

        if commit:
            obj.save()

            if obj.itens.exists():
                for item in obj.itens.all():
                    if obj.equipamento not in item.equipamentos.all():
                        item.equipamentos.add(obj.equipamento)

        return obj

# ================= SICK =================
class SickForm(forms.ModelForm):
    class Meta:
        model = Sick
        fields = ['categoria', 'motivo', 'previsao_retorno']
        widgets = {
            'categoria': forms.TextInput(attrs={'class': 'form-control'}),
            'motivo': forms.Textarea(attrs={'class': 'form-control'}),
            'previsao_retorno': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, equipamento=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.equipamento = equipamento
        self.user = user

    def clean(self):
        cleaned = super().clean()

        if self.equipamento.status == 'TRANSFERENCIA':
            raise ValidationError("Equipamento em transferência não pode ser marcado como SICK.")

        return cleaned

    def save(self, commit=True):
        sick = super().save(commit=False)
        sick.equipamento = self.equipamento

        if commit:
            sick.save()
            self.equipamento.status = 'SICK'
            self.equipamento.save()

        return sick
