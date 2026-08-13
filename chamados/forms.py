from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
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
            'base',
            'inventario',
            'categoria_equipamento',
            'equipamento',
            'lider',
            'titulo',
            'descricao',
            'prioridade',
        ]
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 5}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)

        self.user = user
        hoje = timezone.localdate()

        # BASES PERMITIDAS
        bases = ChamadoAccessPolicy.bases(user)

        self.fields['base'].queryset = (
            bases
            .select_related('empresa')
            .order_by('empresa__nome', 'nome')
        )

        base_selecionada = None

        # USUÁRIO COM UMA ÚNICA BASE
        # A base é sempre determinada pelo backend.
        if bases.count() == 1:
            base_selecionada = bases.first()

            self.fields['base'].initial = (
                base_selecionada
            )

            self.fields['base'].disabled = True

        # USUÁRIO COM MAIS DE UMA BASE
        elif self.is_bound:
            base_id = self.data.get('base')

            if base_id:
                base_selecionada = bases.filter(
                    pk=base_id
                ).first()

        # EDIÇÃO
        elif self.instance and self.instance.pk:
            if (
                    self.instance.base_id
                    and bases.filter(
                pk=self.instance.base_id
            ).exists()
            ):
                base_selecionada = self.instance.base

        # USUÁRIO COM UMA ÚNICA BASE
        elif bases.count() == 1:
            base_selecionada = bases.first()

            self.fields['base'].initial = (
                base_selecionada
            )

        # INVENTÁRIOS
        inventarios = Inventario.objects.none()

        if base_selecionada:
            inventarios = Inventario.objects.filter(
                base=base_selecionada,
                data_inicio=hoje,
                status__in=[
                    'PLANEJADO',
                    'EM_ANDAMENTO',
                ],
            )

        self.fields['inventario'].queryset = (
            inventarios
            .select_related(
                'cliente',
                'base',
                'lider_usuario',
            )
            .order_by(
                'inicio_previsto',
                'loja',
            )
        )

        self.fields['inventario'].required = True

        # INVENTÁRIO INICIAL
        inventario_inicial = None

        if (
            not self.is_bound
            and inventarios.count() == 1
        ):
            inventario_inicial = inventarios.first()

            self.fields['inventario'].initial = (
                inventario_inicial
            )

        # LÍDER
        if inventario_inicial:
            self.fields['lider'].initial = (
                inventario_inicial.lider or ''
            )

        self.fields['lider'].required = False

        # CATEGORIA DO CHAMADO
        self.fields[
            'categoria_equipamento'
        ].required = True

        self.fields[
            'categoria_equipamento'
        ].label = _('Categoria')

        # Descobrir categoria selecionada
        categoria_selecionada = ''

        if self.is_bound:
            categoria_selecionada = (
                self.data.get(
                    'categoria_equipamento'
                )
                or ''
            ).strip()

        elif (
            self.instance
            and self.instance.pk
        ):
            categoria_selecionada = (
                self.instance.categoria_equipamento
                or ''
            )

        # EQUIPAMENTOS
        equipamentos = Equipamento.objects.none()

        if (
            base_selecionada
            and categoria_selecionada
        ):
            equipamentos = Equipamento.objects.filter(
                regional=base_selecionada,
                produto__categoria=categoria_selecionada,
            ).select_related(
                'produto',
                'regional',
            )

            equipamentos = secure_queryset(
                equipamentos,
                user,
            )

        self.fields['equipamento'].queryset = (
            equipamentos.order_by(
                'produto__descricao',
                'patrimonio',
            )
        )

        self.fields['equipamento'].required = categoria_selecionada != 'Sistema'
        self.fields['equipamento'].label = _('Equipamento')

        # CSS
        for field in self.fields.values():
            field.widget.attrs.setdefault(
                'class',
                'form-control'
            )

    def clean(self):
        dados = super().clean()

        base = dados.get('base')
        inventario = dados.get('inventario')

        categoria_equipamento = dados.get(
            'categoria_equipamento'
        )

        equipamento = dados.get(
            'equipamento'
        )

        hoje = timezone.localdate()

        if categoria_equipamento != 'Sistema' and not equipamento:
            self.add_error(
                'equipamento',
                'INFORME O EQUIPAMENTO RELACIONADO AO CHAMADO.'
            )

        # BASE
        if (
            base
            and not ChamadoAccessPolicy.pode_abrir_na_base(
                self.user,
                base,
            )
        ):
            self.add_error(
                'base',
                'VOCÊ NÃO POSSUI ACESSO A ESTA BASE.'
            )

        # INVENTÁRIO / BASE
        if (
            inventario
            and base
            and inventario.base_id != base.pk
        ):
            self.add_error(
                'inventario',
                'O INVENTÁRIO NÃO PERTENCE À BASE SELECIONADA.'
            )

        # INVENTÁRIO / DATA
        if (
            inventario
            and inventario.data_inicio != hoje
        ):
            self.add_error(
                'inventario',
                'SÓ É POSSÍVEL ABRIR CHAMADOS PARA INVENTÁRIOS DO DIA ATUAL.'
            )

        # INVENTÁRIO / STATUS
        status_permitidos = {
            'PLANEJADO',
            'EM_ANDAMENTO',
        }

        if (
            inventario
            and inventario.status
            not in status_permitidos
        ):
            self.add_error(
                'inventario',
                'SÓ É POSSÍVEL ABRIR CHAMADOS PARA INVENTÁRIOS PLANEJADOS OU EM ANDAMENTO.'
            )

        # LÍDER
        if (
            inventario
            and not (
                dados.get('lider')
                or ''
            ).strip()
        ):
            dados['lider'] = (
                inventario.lider
                or ''
            ).strip()

        # EQUIPAMENTO / BASE
        if (
            equipamento
            and base
            and equipamento.regional_id
            != base.pk
        ):
            self.add_error(
                'equipamento',
                'O EQUIPAMENTO NÃO PERTENCE À BASE DO CHAMADO.'
            )

        # EQUIPAMENTO / CATEGORIA
        if (
            equipamento
            and categoria_equipamento
        ):
            if not equipamento.produto:
                self.add_error(
                    'equipamento',
                    'O EQUIPAMENTO NÃO POSSUI PRODUTO VINCULADO.'
                )

            elif (
                equipamento.produto.categoria
                != categoria_equipamento
            ):
                self.add_error(
                    'equipamento',
                    'O EQUIPAMENTO NÃO PERTENCE À CATEGORIA SELECIONADA.'
                )

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
    atendente_novo = forms.ModelChoiceField(
        label=_('Novo atendente'), queryset=User.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    motivo = forms.CharField(
        label=_('Motivo'), widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
    )

    def __init__(self, *args, chamado, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['atendente_novo'].queryset = ChamadoAccessPolicy.atendentes_online_para(chamado).exclude(
            pk=chamado.atendente_id
        )

class ChamadoSickForm(forms.Form):
    diagnostico = forms.CharField(widget=forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}))
