from django import forms
from django.utils.translation import gettext_lazy as _
from estoque.models import Base, Equipamento
from insumos.models import (
    AtivoInsumoIndividualizado,
    CategoriaInsumo,
    CertificadoEpi,
    FornecedorInsumo,
    Insumo,
    Inventario,
    LoteEpi,
    PrecoFornecedorInsumo,
    ProdutoEpi,
    SolicitacaoInsumo,
    VarianteEpi,
)
from django_select2.forms import Select2Widget
from insumos.policies import InsumosTenantPolicy
from insumos.services.certificado_epi_service import CertificadoEpiService


def _obter_ou_criar_variante_epi(*, produto_epi, insumo, tamanho):
    """Reutiliza a variante canônica para permitir novas entradas do mesmo tamanho."""
    nome_canonico = (insumo.descricao or '').strip().upper()
    tamanho_canonico = str(tamanho or '').strip().upper()
    variante, _ = VarianteEpi.objects.get_or_create(
        produto_epi=produto_epi,
        nome=nome_canonico,
        tamanho=tamanho_canonico,
    )
    return variante

class InsumoForm(forms.ModelForm):
    fabricante_importador = forms.CharField(
        required=False,
        label=_('Fabricante / importador'),
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    numero_ca = forms.CharField(
        required=False,
        label=_('Certificado de Aprovação (CA)'),
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    validade_ca = forms.DateField(
        required=False,
        label=_('Validade do CA'),
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    tamanho_variante = forms.CharField(
        required=False,
        label=_('Tamanho / variante'),
        help_text=_('Para EPIs sem numeração, use a identificação aplicável, como P, M ou G.'),
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    tamanho_bota = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=999,
        label=_('Número da bota'),
        help_text=_('Informe somente o número, por exemplo 39.'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'inputmode': 'numeric',
            'min': '1',
            'max': '999',
            'step': '1',
        }),
    )
    base_lote = forms.ModelChoiceField(
        queryset=Base.objects.none(),
        required=False,
        label=_('Base do cadastro'),
        help_text=_(
            'Obrigatória para EPI. CA e tamanho também são obrigatórios; '
            'lote e datas de validade são opcionais.'
        ),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    patrimonio_insumo = forms.CharField(
        required=False,
        max_length=100,
        label=_('Número de patrimônio'),
        help_text=_(
            'Opcional para insumos reutilizáveis ou individualizados. '
            'Cada patrimônio deve ser único em todo o sistema.'
        ),
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    codigo_lote = forms.CharField(
        required=False,
        label=_('Lote'),
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    fabricado_em = forms.DateField(
        required=False,
        label=_('Data de fabricação'),
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    validade_fisica = forms.DateField(
        required=False,
        label=_('Validade física do lote'),
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    observacao_epi = forms.CharField(
        required=False,
        label=_('Observação do EPI'),
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )

    class Meta:
        model = Insumo
        fields = [
            'descricao',
            'imagem_principal',
            'termo_pesquisa_online',
            'categoria',
            'unidade_medida',
            'natureza',
            'forma_controle',
            'estoque_minimo',
            'estoque_maximo',
            'ativo',
            'fabricante_importador',
            'numero_ca',
            'validade_ca',
            'tamanho_variante',
            'tamanho_bota',
            'base_lote',
            'patrimonio_insumo',
            'codigo_lote',
            'fabricado_em',
            'validade_fisica',
            'observacao_epi',
        ]
        labels = {
            'natureza': _('Natureza'),
            'forma_controle': _('Forma de controle'),
        }
        widgets = {
            'descricao': forms.TextInput(attrs={'class': 'form-control'}),
            'imagem_principal': forms.ClearableFileInput(attrs={
                'class': 'form-control', 'accept': 'image/jpeg,image/png,image/webp',
            }),
            'termo_pesquisa_online': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex.: papel sulfite A4 75g 500 folhas',
            }),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'unidade_medida': forms.TextInput(attrs={'class': 'form-control'}),
            'natureza': forms.Select(attrs={'class': 'form-select'}),
            'forma_controle': forms.Select(attrs={'class': 'form-select'}),
            'estoque_minimo': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0', 'max': '10', 'step': '0.01',
            }),
            'estoque_maximo': forms.NumberInput(attrs={'class': 'form-control'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        bases = InsumosTenantPolicy.bases(
            user,
            resource=InsumosTenantPolicy.SUPPLIES,
            action=InsumosTenantPolicy.EDIT,
        ).select_related('empresa').order_by('empresa__nome', 'nome') if user else Base.objects.none()
        self.fields['base_lote'].queryset = bases
        if bases.count() == 1:
            self.fields['base_lote'].initial = bases.first()

        if not self.instance.pk or not hasattr(self.instance, 'dados_epi'):
            return
        produto_epi = self.instance.dados_epi
        certificado = produto_epi.certificados.order_by('-ativo', '-atualizado_em').first()
        variante = produto_epi.variantes.order_by('-ativo', 'tamanho').first()
        lote = produto_epi.lotes.filter(base__in=bases).order_by(
            '-ativo', '-atualizado_em',
        ).first()
        self.fields['fabricante_importador'].initial = produto_epi.fabricante_importador
        self.fields['observacao_epi'].initial = produto_epi.observacao
        if certificado:
            self.fields['numero_ca'].initial = certificado.numero_ca
            self.fields['validade_ca'].initial = certificado.validade_ca
        if variante:
            tamanho = variante.tamanho or variante.nome
            if 'BOTA' in (self.instance.descricao or '').upper() and tamanho.isdigit():
                self.fields['tamanho_bota'].initial = int(tamanho)
            else:
                self.fields['tamanho_variante'].initial = tamanho
        if lote:
            self.fields['base_lote'].initial = lote.base_id
            self.fields['codigo_lote'].initial = lote.codigo_lote
            self.fields['fabricado_em'].initial = lote.fabricado_em
            self.fields['validade_fisica'].initial = lote.validade_fisica

    def clean(self):
        cleaned = super().clean()
        self.caepi_resultado = None
        if (
            cleaned.get('natureza') == Insumo.Natureza.EPI
            and not cleaned.get('base_lote')
        ):
            self.add_error(
                'base_lote',
                _('Selecione a Base em que o EPI será cadastrado.'),
            )
        if cleaned.get('natureza') == Insumo.Natureza.EPI:
            numero_ca = (cleaned.get('numero_ca') or '').strip()
            if not numero_ca:
                self.add_error(
                    'numero_ca',
                    _('Informe o CA do EPI.'),
                )
            else:
                from integracao.clients.caepi import CaepiLookupStatus
                from integracao.services.caepi_service import CaepiService

                resultado = CaepiService().consultar(numero_ca)
                if resultado.status == CaepiLookupStatus.FOUND:
                    self.caepi_resultado = resultado
                    cleaned['validade_ca'] = resultado.validade_ca
            descricao = (cleaned.get('descricao') or '').strip().upper()
            if 'BOTA' in descricao:
                if cleaned.get('tamanho_bota') is None:
                    self.add_error(
                        'tamanho_bota',
                        _('Informe o número da bota.'),
                    )
            elif not (cleaned.get('tamanho_variante') or '').strip():
                self.add_error('tamanho_variante', _('Informe o tamanho ou a variante do EPI.'))
        patrimonio = (cleaned.get('patrimonio_insumo') or '').strip().upper()
        permite_patrimonio = (
            cleaned.get('natureza') == Insumo.Natureza.REUTILIZAVEL
            or cleaned.get('forma_controle') == Insumo.FormaControle.INDIVIDUALIZADO
        )
        if patrimonio and not permite_patrimonio:
            self.add_error(
                'patrimonio_insumo',
                _('Patrimônio só pode ser informado para item reutilizável ou individualizado.'),
            )
        if patrimonio and not cleaned.get('base_lote'):
            self.add_error(
                'base_lote',
                _('Selecione a Base do ativo patrimonial.'),
            )
        if patrimonio and AtivoInsumoIndividualizado.objects.filter(
            patrimonio__iexact=patrimonio,
        ).exists():
            self.add_error(
                'patrimonio_insumo',
                _('Este número de patrimônio já está cadastrado.'),
            )
        if patrimonio and Equipamento.objects.filter(
            patrimonio__iexact=patrimonio,
        ).exists():
            self.add_error(
                'patrimonio_insumo',
                _('Este número de patrimônio já pertence a um equipamento.'),
            )
        tem_dados_lote = any(cleaned.get(campo) for campo in (
            'codigo_lote', 'fabricado_em', 'validade_fisica',
        ))
        if (
            cleaned.get('natureza') != Insumo.Natureza.EPI
            and tem_dados_lote
            and not cleaned.get('base_lote')
        ):
            self.add_error(
                'base_lote',
                _('Selecione a Base apenas quando informar dados de lote.'),
            )
        fabricado_em = cleaned.get('fabricado_em')
        validade_fisica = cleaned.get('validade_fisica')
        if fabricado_em and validade_fisica and validade_fisica < fabricado_em:
            self.add_error(
                'validade_fisica',
                _('A validade física não pode ser anterior à fabricação.'),
            )
        return cleaned

    def clean_imagem_principal(self):
        imagem = self.cleaned_data.get('imagem_principal')
        if imagem and getattr(imagem, 'size', 0) > 5 * 1024 * 1024:
            raise forms.ValidationError(_('A imagem deve ter no máximo 5 MB.'))
        return imagem

    def save(self, commit=True):
        insumo = super().save(commit=commit)
        if not commit:
            return insumo

        base = self.cleaned_data.get('base_lote')
        patrimonio = (self.cleaned_data.get('patrimonio_insumo') or '').strip().upper()
        if base and patrimonio:
            ativo = AtivoInsumoIndividualizado(
                base=base,
                insumo=insumo,
                patrimonio=patrimonio,
            )
            ativo.full_clean()
            ativo.save()

        if insumo.natureza != Insumo.Natureza.EPI:
            return insumo

        produto_epi, _ = ProdutoEpi.objects.get_or_create(
            insumo=insumo,
            defaults={
                'fabricante_importador': self.cleaned_data.get(
                    'fabricante_importador',
                ) or '',
            },
        )
        produto_epi.fabricante_importador = (
            self.cleaned_data.get('fabricante_importador') or ''
        ).strip()
        produto_epi.observacao = (
            self.cleaned_data.get('observacao_epi') or ''
        ).strip()
        produto_epi.full_clean()
        produto_epi.save()

        certificado = None
        numero_ca = self.cleaned_data.get('numero_ca')
        if numero_ca:
            from integracao.models import CaepiImportacao

            resultado = getattr(self, 'caepi_resultado', None)
            snapshot = None
            importacao = None
            if resultado is not None:
                snapshot = {
                    'numero_ca': resultado.numero_ca,
                    'validade_ca': resultado.validade_ca.isoformat() if resultado.validade_ca else '',
                    'situacao': resultado.situacao,
                    'natureza': resultado.natureza,
                    'produto': resultado.produto,
                    'descricao': resultado.descricao,
                    'marca': resultado.marca,
                    'referencia': resultado.referencia,
                    'cor': resultado.cor,
                    'aprovado_para': resultado.aprovado_para,
                    'restricao': resultado.restricao,
                    'observacao_analise': resultado.observacao_analise,
                    'numero_laudo': resultado.numero_laudo,
                    'norma': resultado.norma,
                    'ocorrencias': resultado.ocorrencias,
                }
                importacao = CaepiImportacao.objects.filter(
                    status=CaepiImportacao.Status.PUBLICADA,
                ).first()
            certificado = CertificadoEpiService.registrar(
                produto_epi=produto_epi,
                numero_ca=numero_ca,
                validade_ca=self.cleaned_data.get('validade_ca'),
                situacao_oficial=resultado.situacao if resultado else '',
                snapshot_oficial=snapshot,
                consultado_em=timezone.now() if resultado else None,
                importacao_caepi=importacao,
            )

        variante = None
        tamanho_bota = self.cleaned_data.get('tamanho_bota')
        tamanho = (
            str(tamanho_bota)
            if tamanho_bota is not None
            else (self.cleaned_data.get('tamanho_variante') or '').strip()
        )
        if tamanho:
            variante = _obter_ou_criar_variante_epi(
                produto_epi=produto_epi,
                insumo=insumo,
                tamanho=tamanho,
            )

        if base:
            codigo_lote = (self.cleaned_data.get('codigo_lote') or '').strip().upper()
            lote, _ = LoteEpi.objects.update_or_create(
                base=base,
                produto_epi=produto_epi,
                variante=variante,
                codigo_lote=codigo_lote,
                defaults={
                    'certificado': certificado,
                    'fabricado_em': self.cleaned_data.get('fabricado_em'),
                    'validade_fisica': self.cleaned_data.get('validade_fisica'),
                    'observacao': self.cleaned_data.get('observacao_epi') or '',
                    'ativo': True,
                },
            )
            lote.full_clean()
            lote.save()
        return insumo

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
            'empresa', 'insumo', 'fornecedor', 'valor_unitario', 'vigente_desde',
            'vigente_ate', 'ativo', 'observacao',
        ]
        labels = {
            'empresa': _('Empresa'),
            'insumo': _('Insumo'),
            'fornecedor': _('Fornecedor'),
            'valor_unitario': _('Preço unitário'),
            'vigente_desde': _('Vigente desde'),
            'vigente_ate': _('Vigente até'),
            'ativo': _('Ativo'),
            'observacao': _('Observação'),
        }
        widgets = {
            'empresa': forms.Select(attrs={'class': 'form-select'}),
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

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        empresas = InsumosTenantPolicy.empresas(
            user,
            action=InsumosTenantPolicy.EDIT,
        ).order_by('nome')
        self.fields['empresa'].queryset = empresas
        self.fields['empresa'].required = True
        perfil = getattr(user, 'perfil', None)
        if self.instance.pk and self.instance.empresa_id:
            self.fields['empresa'].initial = self.instance.empresa_id
        elif perfil and perfil.empresa_id and empresas.filter(
            pk=perfil.empresa_id,
        ).exists():
            self.fields['empresa'].initial = perfil.empresa_id
        elif empresas.count() == 1:
            self.fields['empresa'].initial = empresas.first().pk

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
        if user:
            self.fields['base'].queryset = InsumosTenantPolicy.bases(
                user,
                resource=InsumosTenantPolicy.SUPPLIES,
                action=InsumosTenantPolicy.CREATE,
            ).order_by('nome')
        else:
            self.fields['base'].queryset = Base.objects.none()

class CadastroInsumoForm(forms.Form):

    base = forms.ModelChoiceField(queryset=Base.objects.all(), widget=forms.Select(attrs={'class': 'form-select'}))
    categoria = forms.ModelChoiceField(queryset=CategoriaInsumo.objects.all().order_by('nome'), widget=forms.Select(attrs={'class': 'form-select'}))
    insumo = forms.ModelChoiceField(queryset=Insumo.objects.none(), widget=forms.Select(attrs={'class': 'form-select'}))
    quantidade = forms.DecimalField(min_value=1, decimal_places=2, max_digits=10, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    numero_ca = forms.CharField(
        required=False,
        label=_('Certificado de Aprovação (CA)'),
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    validade_ca = forms.DateField(
        required=False,
        label=_('Validade do CA'),
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    tamanho_variante = forms.CharField(
        required=False,
        label=_('Tamanho / variante'),
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    tamanho_bota = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=999,
        label=_('Número da bota'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 'min': '1', 'max': '999', 'step': '1',
        }),
    )
    codigo_lote = forms.CharField(
        required=False,
        label=_('Lote'),
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    fabricado_em = forms.DateField(
        required=False,
        label=_('Data de fabricação'),
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    validade_fisica = forms.DateField(
        required=False,
        label=_('Validade física'),
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    patrimonio = forms.CharField(
        required=False,
        max_length=100,
        label=_('Número de patrimônio'),
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )

    def __init__(self, *args, user=None, **kwargs):

        super().__init__(*args, **kwargs)

        if user:
            self.fields['base'].queryset = InsumosTenantPolicy.bases(
                user,
                resource=InsumosTenantPolicy.SUPPLIES,
                action=InsumosTenantPolicy.MOVE,
            ).order_by('nome')
        else:
            self.fields['base'].queryset = Base.objects.none()

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

    @staticmethod
    def _eh_bota(insumo):
        return bool(insumo and 'BOTA' in (insumo.descricao or '').upper())

    @staticmethod
    def _categoria_operacional(insumo):
        return bool(
            insumo
            and (insumo.categoria.nome or '').strip().upper() == 'OPERACIONAL'
        )

    def clean(self):
        cleaned = super().clean()
        insumo = cleaned.get('insumo')
        quantidade = cleaned.get('quantidade')
        if not insumo:
            return cleaned

        if insumo.natureza == Insumo.Natureza.EPI:
            numero_ca = (cleaned.get('numero_ca') or '').strip()
            if not numero_ca:
                self.add_error('numero_ca', _('Informe o CA do EPI.'))
            else:
                certificado_existente = CertificadoEpi.objects.filter(
                    numero_ca__iexact=numero_ca,
                ).select_related('produto_epi').first()
                if (
                    certificado_existente
                    and certificado_existente.produto_epi.insumo_id != insumo.id
                ):
                    self.add_error(
                        'numero_ca',
                        _(
                            'Este CA já está associado a outro produto EPI. '
                            'Selecione o produto correto.'
                        ),
                    )
                if 'numero_ca' not in self.errors:
                    from integracao.clients.caepi import CaepiLookupStatus
                    from integracao.services.caepi_service import CaepiService

                    resultado = CaepiService().consultar(numero_ca)
                    if resultado.status == CaepiLookupStatus.FOUND:
                        self.caepi_resultado = resultado
                        cleaned['validade_ca'] = resultado.validade_ca
            if self._eh_bota(insumo):
                if cleaned.get('tamanho_bota') is None:
                    self.add_error('tamanho_bota', _('Informe o número da bota.'))
            elif not (cleaned.get('tamanho_variante') or '').strip():
                self.add_error(
                    'tamanho_variante',
                    _('Informe o tamanho ou a variante do EPI.'),
                )

            fabricado_em = cleaned.get('fabricado_em')
            validade_fisica = cleaned.get('validade_fisica')
            if fabricado_em and validade_fisica and validade_fisica < fabricado_em:
                self.add_error(
                    'validade_fisica',
                    _('A validade física não pode ser anterior à fabricação.'),
                )

        patrimonio = (cleaned.get('patrimonio') or '').strip().upper()
        permite_patrimonio = (
            self._categoria_operacional(insumo)
            or insumo.natureza == Insumo.Natureza.REUTILIZAVEL
            or insumo.forma_controle == Insumo.FormaControle.INDIVIDUALIZADO
        )
        if patrimonio and not permite_patrimonio:
            self.add_error(
                'patrimonio',
                _('Patrimônio só pode ser informado para item operacional, reutilizável ou individualizado.'),
            )
        if patrimonio and quantidade != 1:
            self.add_error(
                'quantidade',
                _('A quantidade deve ser 1 quando um patrimônio for informado.'),
            )
        if patrimonio and AtivoInsumoIndividualizado.objects.filter(
            patrimonio__iexact=patrimonio,
        ).exists():
            self.add_error('patrimonio', _('Este número de patrimônio já está cadastrado.'))
        if patrimonio and Equipamento.objects.filter(
            patrimonio__iexact=patrimonio,
        ).exists():
            self.add_error(
                'patrimonio',
                _('Este número de patrimônio já pertence a um equipamento.'),
            )
        return cleaned

    def criar_vinculos_da_entrada(self):
        """Cria metadados e devolve os vínculos para a movimentação."""
        insumo = self.cleaned_data['insumo']
        base = self.cleaned_data['base']
        lote_epi = None
        ativo_individualizado = None

        if insumo.natureza == Insumo.Natureza.EPI:
            from django.utils import timezone
            from integracao.models import CaepiImportacao

            produto_epi, _ = ProdutoEpi.objects.get_or_create(insumo=insumo)
            resultado = getattr(self, 'caepi_resultado', None)
            snapshot = None
            importacao = None
            if resultado is not None:
                snapshot = {
                    'numero_ca': resultado.numero_ca,
                    'validade_ca': (
                        resultado.validade_ca.isoformat() if resultado.validade_ca else ''
                    ),
                    'situacao': resultado.situacao,
                    'natureza': resultado.natureza,
                    'produto': resultado.produto,
                    'descricao': resultado.descricao,
                    'marca': resultado.marca,
                    'referencia': resultado.referencia,
                    'cor': resultado.cor,
                    'aprovado_para': resultado.aprovado_para,
                    'restricao': resultado.restricao,
                    'observacao_analise': resultado.observacao_analise,
                    'numero_laudo': resultado.numero_laudo,
                    'norma': resultado.norma,
                    'ocorrencias': resultado.ocorrencias,
                }
                importacao = CaepiImportacao.objects.filter(
                    status=CaepiImportacao.Status.PUBLICADA,
                ).first()
            certificado = CertificadoEpiService.registrar(
                produto_epi=produto_epi,
                numero_ca=self.cleaned_data['numero_ca'],
                validade_ca=self.cleaned_data.get('validade_ca'),
                situacao_oficial=resultado.situacao if resultado else '',
                snapshot_oficial=snapshot,
                consultado_em=timezone.now() if resultado else None,
                importacao_caepi=importacao,
            )
            tamanho_bota = self.cleaned_data.get('tamanho_bota')
            tamanho = (
                str(tamanho_bota)
                if tamanho_bota is not None
                else (self.cleaned_data.get('tamanho_variante') or '').strip()
            )
            variante = _obter_ou_criar_variante_epi(
                produto_epi=produto_epi,
                insumo=insumo,
                tamanho=tamanho,
            )
            codigo_lote = (self.cleaned_data.get('codigo_lote') or '').strip().upper()
            lote_epi, _ = LoteEpi.objects.update_or_create(
                base=base,
                produto_epi=produto_epi,
                variante=variante,
                codigo_lote=codigo_lote,
                defaults={
                    'certificado': certificado,
                    'fabricado_em': self.cleaned_data.get('fabricado_em'),
                    'validade_fisica': self.cleaned_data.get('validade_fisica'),
                    'ativo': True,
                },
            )
            lote_epi.full_clean()
            lote_epi.save()

        patrimonio = (self.cleaned_data.get('patrimonio') or '').strip().upper()
        if patrimonio:
            if self._categoria_operacional(insumo) and not (
                insumo.natureza == Insumo.Natureza.REUTILIZAVEL
                or insumo.forma_controle == Insumo.FormaControle.INDIVIDUALIZADO
            ):
                insumo.natureza = Insumo.Natureza.REUTILIZAVEL
                insumo.forma_controle = Insumo.FormaControle.INDIVIDUALIZADO
                insumo.save(update_fields=['natureza', 'forma_controle'])
            ativo_individualizado = AtivoInsumoIndividualizado(
                base=base,
                insumo=insumo,
                patrimonio=patrimonio,
            )
            ativo_individualizado.save()

        return lote_epi, ativo_individualizado

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
