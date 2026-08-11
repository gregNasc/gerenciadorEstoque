from django import forms

from django.contrib.auth.models import User

from chamados.models import CategoriaChamado, Chamado
from chamados.policies import ChamadoAccessPolicy
from estoque.models import Equipamento
from estoque.security import secure_queryset
from insumos.models import Inventario


class ChamadoForm(forms.ModelForm):
    class Meta:
        model = Chamado
        fields = [
            'base', 'inventario', 'equipamento', 'categoria', 'loja', 'lider', 'titulo',
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
        inventarios = Inventario.objects.filter(
            base__in=bases
        )
        perfil = getattr(user, 'perfil', None)
        if perfil and perfil.is_operador and not ChamadoAccessPolicy.pode_atender(user):
            inventarios = inventarios.filter(lider_usuario=user)
        self.fields['inventario'].queryset = inventarios.select_related(
            'cliente', 'base'
        ).order_by('-data_inicio', 'loja')[:1000]
        self.fields['inventario'].required = True
        self.fields['equipamento'].queryset = secure_queryset(
            Equipamento.objects.filter(regional__in=bases).select_related('produto', 'regional'),
            user,
        ).order_by('codigo')
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
        equipamento = dados.get('equipamento')
        if equipamento and base and equipamento.regional_id != base.pk:
            self.add_error('equipamento', 'O EQUIPAMENTO NÃO PERTENCE À BASE SELECIONADA.')
        return dados


class ChamadoMensagemForm(forms.Form):
    texto = forms.CharField(widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}))
    nota_interna = forms.BooleanField(required=False)
    anexo = forms.FileField(required=False)


class ChamadoStatusForm(forms.Form):
    status = forms.ChoiceField(choices=Chamado.Status.choices)
    resolucao = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 3}))
    causa_raiz = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 3}))

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
        if dados.get('status') == Chamado.Status.RESOLVIDO:
            if not (dados.get('resolucao') or '').strip():
                self.add_error('resolucao', 'INFORME A SOLUÇÃO DO CHAMADO.')
            if not (dados.get('causa_raiz') or '').strip():
                self.add_error('causa_raiz', 'INFORME A CAUSA RAIZ DO CHAMADO.')
        return dados


class ChamadoAvaliacaoForm(forms.Form):
    nota = forms.IntegerField(min_value=1, max_value=5, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    resolvido = forms.TypedChoiceField(
        choices=((True, 'SIM, FOI RESOLVIDO'), (False, 'NÃO, PRECISA SER REABERTO')),
        coerce=lambda valor: str(valor).lower() == 'true',
        widget=forms.RadioSelect,
    )
    comentario = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}))


class ChamadoTransferenciaForm(forms.Form):
    atendente_novo = forms.ModelChoiceField(queryset=User.objects.none(), widget=forms.Select(attrs={'class': 'form-select'}))
    motivo = forms.CharField(widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}))

    def __init__(self, *args, chamado, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['atendente_novo'].queryset = ChamadoAccessPolicy.atendentes_para(chamado).exclude(
            pk=chamado.atendente_id
        )


class ChamadoSickForm(forms.Form):
    diagnostico = forms.CharField(widget=forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}))
