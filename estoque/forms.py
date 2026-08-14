from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import DeclaracaoCorreios, DeclaracaoCorreiosItem, Produto, Equipamento, Transferencia, Sick, Base
from estoque.models import Base
from django.utils.translation import gettext_lazy as _


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
    class Meta:
        model = Produto
        fields = [
            'codigo', 'descricao', 'nome_resumido', 'fabricante', 'modelo',
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
        if Produto.objects.filter(codigo=codigo).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Já existe um produto com esse código.")
        return codigo

# ================= EQUIPAMENTO =================
class EquipamentoForm(forms.ModelForm):

    categoria = forms.ChoiceField(
        choices=[
            ('', _('Selecione')),
            ('Coletores', _('Coletores')),
            ('Impressoras', _('Impressoras')),
            ('Notebooks', _('Notebooks')),
            ('Routers', _('Routers')),
        ],
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

        self.fields['produto'].queryset = Produto.objects.none()

        if 'categoria' in self.data:
            try:
                categoria = self.data.get('categoria')
                self.fields['produto'].queryset = Produto.objects.filter(categoria=categoria)
            except:
                pass

        elif self.instance.pk:
            self.fields['produto'].queryset = Produto.objects.filter(
                categoria=self.instance.produto.categoria
            )

        if user and not user.is_superuser:
            perfil = getattr(user, 'perfil', None)

            if perfil:
                from estoque.policies.compras import ComprasAccessPolicy
                if perfil.is_admin:
                    self.fields['regional'].queryset = Base.objects.all()
                elif perfil.is_compras_insumos:
                    self.fields['regional'].queryset = ComprasAccessPolicy.bases(user)
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
        if not perfil.is_admin and not perfil.regionais.filter(pk=regional.pk).exists():
            raise ValidationError("Você não possui acesso a esta base.")
        if self.base_selecionada and regional.pk != self.base_selecionada.pk:
            raise ValidationError("A base informada diverge do contexto selecionado.")
        return regional

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
