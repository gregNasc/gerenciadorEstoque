from pathlib import Path

from django import forms

from estoque.models import VideoDocumentacao
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
