from pathlib import Path

from django import forms

from estoque.models import ResolucaoDocumento, VideoDocumentacao
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
            'titulo', 'fabricante', 'modelo', 'categoria', 'resumo', 'tags', 'arquivo',
        ]
        labels = {
            'titulo': 'Título do relatório',
            'arquivo': 'Relatório em PDF',
            'tags': 'Palavras-chave',
        }
        help_texts = {
            'tags': 'Separe os sintomas por vírgulas, por exemplo: Wi-Fi, scanner, travamento.',
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
            raise forms.ValidationError('Selecione um relatório em PDF para enviar.')
        arquivo = self.cleaned_data['arquivo']
        if Path(arquivo.name).suffix.lower() != '.pdf':
            raise forms.ValidationError('Envie um arquivo PDF.')
        if arquivo.size > 20 * 1024 * 1024:
            raise forms.ValidationError('O arquivo deve ter no máximo 20 MB.')
        assinatura = arquivo.read(5)
        arquivo.seek(0)
        if assinatura != b'%PDF-':
            raise forms.ValidationError('O arquivo enviado não é um PDF válido.')
        return arquivo


class VideoDocumentacaoForm(forms.ModelForm):
    class Meta:
        model = VideoDocumentacao
        fields = [
            'titulo', 'descricao', 'url', 'origem', 'produto_codigo', 'categoria',
            'tags', 'duracao', 'publicado_em',
        ]
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 3}),
            'publicado_em': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault('class', 'form-control')
