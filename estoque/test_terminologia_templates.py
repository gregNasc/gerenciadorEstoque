import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class TerminologiaTemplatesTests(SimpleTestCase):
    TERMO_TECNICO = re.compile(r'\btenant\b', re.IGNORECASE)

    @staticmethod
    def _exclusivo_superadmin(caminho):
        relativo = caminho.relative_to(settings.BASE_DIR).as_posix()
        return bool(
            relativo == 'estoque/templates/estoque/painel_superuser.html'
            or relativo == 'estoque/templates/estoque/onboarding_empresa.html'
            or relativo.startswith('estoque/templates/estoque/onboarding/')
        )

    def test_termo_tecnico_nao_aparece_em_templates_comuns(self):
        ocorrencias = []
        for caminho in Path(settings.BASE_DIR).glob('**/templates/**/*.html'):
            if self._exclusivo_superadmin(caminho):
                continue
            conteudo = caminho.read_text(encoding='utf-8')
            for numero, linha in enumerate(conteudo.splitlines(), start=1):
                if self.TERMO_TECNICO.search(linha):
                    ocorrencias.append(
                        f'{caminho.relative_to(settings.BASE_DIR)}:{numero}'
                    )
        self.assertEqual(
            ocorrencias,
            [],
            'Use "empresa" ou "grupo empresarial" nos templates comuns: '
            + ', '.join(ocorrencias),
        )
