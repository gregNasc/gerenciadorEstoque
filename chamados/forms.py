from django import forms

from chamados.models import CategoriaChamado, Chamado
from chamados.policies import ChamadoAccessPolicy
from insumos.models import Inventario


class ChamadoForm(forms.ModelForm):
    class Meta:
        model = Chamado
        fields = [
            'base', 'inventario', 'categoria', 'loja', 'lider', 'titulo',
            'descricao', 'prioridade',
        ]
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 5}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        bases = ChamadoAccessPolicy.bases(user)
        self.fields['base'].queryset = bases.select_related('empresa').order_by('empresa__nome', 'nome')
        self.fields['inventario'].queryset = Inventario.objects.filter(
            base__in=bases
        ).select_related('cliente', 'base').order_by('-data_inicio', 'loja')[:1000]
        self.fields['categoria'].queryset = CategoriaChamado.objects.filter(ativo=True)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')

    def clean(self):
        dados = super().clean()
        base = dados.get('base')
        inventario = dados.get('inventario')
        if base and not ChamadoAccessPolicy.pode_abrir_na_base(self.user, base):
            self.add_error('base', 'VOCÊ NÃO POSSUI ACESSO A ESTA BASE.')
        if inventario and base and inventario.base_id != base.pk:
            self.add_error('inventario', 'O INVENTÁRIO NÃO PERTENCE À BASE SELECIONADA.')
        return dados


class ChamadoMensagemForm(forms.Form):
    texto = forms.CharField(widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}))
    nota_interna = forms.BooleanField(required=False)
    anexo = forms.FileField(required=False)


class ChamadoStatusForm(forms.Form):
    status = forms.ChoiceField(choices=Chamado.Status.choices)
    resolucao = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 3}))

    def __init__(self, *args, status_permitidos=None, **kwargs):
        super().__init__(*args, **kwargs)
        permitidos = set(status_permitidos or [])
        self.fields['status'].choices = [
            item for item in Chamado.Status.choices if item[0] in permitidos
        ]
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')

    def clean(self):
        dados = super().clean()
        if dados.get('status') in {Chamado.Status.RESOLVIDO, Chamado.Status.FECHADO}:
            if not (dados.get('resolucao') or '').strip():
                self.add_error('resolucao', 'INFORME A RESOLUÇÃO DO CHAMADO.')
        return dados
