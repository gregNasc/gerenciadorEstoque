import posixpath
from urllib.parse import unquote, urlsplit

from django.conf import settings
from django.http import HttpResponseNotFound


class LegacyDocumentationStaticMiddleware:
    """Reserva o acervo legado para os endpoints autenticados da aplicação."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = posixpath.normpath(unquote(request.path_info))
        prefix = urlsplit(settings.STATIC_URL).path.rstrip('/')
        if any(path.startswith(f'{prefix}/{folder}/') for folder in ('manuais', 'documentacao')):
            return HttpResponseNotFound()
        return self.get_response(request)
