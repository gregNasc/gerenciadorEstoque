from pathlib import Path

from django import forms
from django.utils.translation import gettext_lazy as _

from estoque.models import (
    DRIVER_IMPRESSORA_EXTENSOES,
    DRIVER_IMPRESSORA_TAMANHO_MAXIMO,
    DriverImpressora,
    ResolucaoDocumento,
    VideoDocumentacao,
)
from insumos.models import ClienteChecklistDocumento


class ClienteChecklistUploadForm(forms.ModelForm):
    class Meta:
        model = ClienteChecklistDocumento
        fields = ['arquivo']
        labels = {'arquivo': 'Arquivo do checklist'}
        widgets = {
            'arquivo': forms.ClearableFileInput(
                attrs={
                    'class': 'form-control',
                    'accept': '.pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                }
            )
        }

    def clean_arquivo(self):
        if self.is_bound and 'arquivo' not in self.files:
            raise forms.ValidationError('Selecione um arquivo para enviar.')
        arquivo = self.cleaned_data['arquivo']
        extensao = Path(arquivo.name).suffix.lower()
        if extensao not in {'.pdf', '.doc', '.docx'}:
            raise forms.ValidationError('Envie um arquivo PDF ou Word (.pdf, .doc ou .docx).')
        if arquivo.size > 20 * 1024 * 1024:
            raise forms.ValidationError('O arquivo deve ter no máximo 20 MB.')
        return arquivo


class ResolucaoDocumentoForm(forms.ModelForm):
    class Meta:
        model = ResolucaoDocumento
        fields = [
            'titulo', 'fabricante', 'modelo', 'categoria', 'idioma', 'resumo',
            'tags', 'arquivo',
        ]
        labels = {
            'titulo': _('Título do relatório'),
            'fabricante': _('Fabricante'),
            'modelo': _('Modelo'),
            'categoria': _('Categoria'),
            'arquivo': _('Relatório em PDF'),
            'resumo': _('Resumo'),
            'tags': _('Palavras-chave'),
            'idioma': _('Idioma do documento'),
        }
        help_texts = {
            'tags': _('Separe os sintomas por vírgulas, por exemplo: Wi-Fi, scanner, travamento.'),
        }
        widgets = {
            'resumo': forms.Textarea(attrs={'rows': 3}),
            'arquivo': forms.ClearableFileInput(
                attrs={'accept': '.pdf,application/pdf'}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault('class', 'form-control')

    def clean_arquivo(self):
        if self.is_bound and 'arquivo' not in self.files:
            raise forms.ValidationError(_('Selecione um relatório em PDF para enviar.'))
        arquivo = self.cleaned_data['arquivo']
        if Path(arquivo.name).suffix.lower() != '.pdf':
            raise forms.ValidationError(_('Envie um arquivo PDF.'))
        if arquivo.size > 20 * 1024 * 1024:
            raise forms.ValidationError(_('O arquivo deve ter no máximo 20 MB.'))
        assinatura = arquivo.read(5)
        arquivo.seek(0)
        if assinatura != b'%PDF-':
            raise forms.ValidationError(_('O arquivo enviado não é um PDF válido.'))
        return arquivo


class VideoDocumentacaoForm(forms.ModelForm):
    class Meta:
        model = VideoDocumentacao
        fields = [
            'titulo', 'descricao', 'url', 'origem', 'produto_codigo', 'categoria',
            'tags', 'duracao', 'publicado_em',
        ]
        labels = {
            'titulo': _('Título'),
            'descricao': _('Descrição'),
            'url': _('URL do vídeo'),
            'origem': _('Origem'),
            'produto_codigo': _('Código do produto'),
            'categoria': _('Categoria'),
            'tags': _('Palavras-chave'),
            'duracao': _('Duração'),
            'publicado_em': _('Data de publicação'),
        }
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 3}),
            'publicado_em': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault('class', 'form-control')


class DriverImpressoraForm(forms.ModelForm):
    class Meta:
        model = DriverImpressora
        fields = [
            'titulo', 'fabricante', 'modelo', 'sistema_operacional',
            'arquitetura', 'versao', 'descricao', 'instrucoes', 'arquivo',
        ]
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 3}),
            'instrucoes': forms.Textarea(attrs={'rows': 4}),
            'arquivo': forms.ClearableFileInput(
                attrs={'accept': '.exe,.msi,.zip,.rar,.cab,.inf'}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault('class', 'form-control')

    def clean_arquivo(self):
        if self.is_bound and 'arquivo' not in self.files:
            raise forms.ValidationError(_('Selecione um arquivo de driver para enviar.'))
        arquivo = self.cleaned_data['arquivo']
        extensao = Path(arquivo.name).suffix.lower()
        extensoes = {f'.{item}' for item in DRIVER_IMPRESSORA_EXTENSOES}
        if extensao not in extensoes:
            raise forms.ValidationError(
                _('Envie um driver nos formatos EXE, MSI, ZIP, RAR, CAB ou INF.')
            )
        if arquivo.size > DRIVER_IMPRESSORA_TAMANHO_MAXIMO:
            raise forms.ValidationError(_('O arquivo deve ter no máximo 500 MB.'))
        return arquivo
