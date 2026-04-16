from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Produto, Equipamento, Transferencia, Sick, Base
from estoque.models import Base

# ================= PRODUTO =================
class ProdutoForm(forms.ModelForm):
    class Meta:
        model = Produto
        fields = ['codigo', 'descricao', 'fabricante', 'modelo']
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
            ('', 'Selecione'),
            ('Coletores', 'Coletores'),
            ('Impressoras', 'Impressoras'),
            ('Notebooks', 'Notebooks'),
            ('Routers', 'Routers'),
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
            'responsavel',
            'foto'
        ]
        widgets = {
            'produto': forms.Select(attrs={'class': 'form-control'}),
            'numero_serie': forms.TextInput(attrs={'class': 'form-control'}),
            'patrimonio': forms.TextInput(attrs={'class': 'form-control'}),
            'regional': forms.Select(attrs={'class': 'form-control'}),
            'responsavel': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

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
                if perfil.is_admin:
                    self.fields['regional'].queryset = Base.objects.all()
                else:
                    regionais = perfil.regionais.all()

                    self.fields['regional'].queryset = regionais

                    if regionais.count() == 1:
                        self.fields['regional'].initial = regionais.first()

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
            status='PENDENTE'
        ).exists():
            raise ValidationError("Já existe uma transferência pendente.")

        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)

        obj.equipamento = self.equipamento
        obj.regional_origem = self.equipamento.regional
        obj.solicitado_por = self.user
        obj.solicitacao = None  # será vinculado no fluxo automático depois

        if commit:
            obj.save()

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
