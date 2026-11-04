from pathlib import Path
from uuid import uuid4

from django.core.files.storage import Storage, storages


class DocumentoCompraStorage(Storage):
    """Grava documentos em storage privado e mantém leitura do legado."""

    @property
    def privado(self):
        return storages['private']

    @property
    def legado(self):
        return storages['default']

    def _storage_leitura(self, name):
        if self.privado.exists(name):
            return self.privado
        return self.legado

    def _open(self, name, mode='rb'):
        return self._storage_leitura(name).open(name, mode)

    def _save(self, name, content):
        return self.privado.save(name, content)

    def exists(self, name):
        return self.privado.exists(name) or self.legado.exists(name)

    def size(self, name):
        return self._storage_leitura(name).size(name)

    def delete(self, name):
        if self.privado.exists(name):
            self.privado.delete(name)
        if self.legado.exists(name):
            self.legado.delete(name)

    def get_available_name(self, name, max_length=None):
        return self.privado.get_available_name(name, max_length=max_length)

    def get_valid_name(self, name):
        return self.privado.get_valid_name(name)

    def url(self, name):
        raise ValueError(
            'Documentos de compra não possuem URL pública. Use a rota autorizada.'
        )


def documento_compra_storage():
    return DocumentoCompraStorage()


def documento_compra_upload_to(instance, filename):
    extensao = Path(filename).suffix.lower()
    tipo = 'xml' if extensao == '.xml' else 'danfe'
    empresa_id = instance.empresa_id or 'sem-empresa'
    return f'compras/{empresa_id}/{tipo}/{uuid4().hex}{extensao}'
