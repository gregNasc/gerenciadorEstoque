from cryptography.fernet import Fernet
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        'Gera uma nova entrada Fernet para LINHAS_MOVEIS_CREDENTIAL_KEYS. '
        'Apenas imprime; não altera .env, Render ou SECRET_KEY.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--id', default='v1', dest='key_id')

    def handle(self, *args, **options):
        key_id = options['key_id'].strip()
        if not key_id or any(not (char.isalnum() or char in '_.-') for char in key_id):
            self.stderr.write(self.style.ERROR('O identificador aceita letras, números, _, . e -.'))
            return
        chave = Fernet.generate_key().decode('ascii')
        self.stdout.write(f'{key_id}:{chave}')
        self.stderr.write(
            'A chave foi apenas exibida. Armazene-a como secret; não a versione nem remova '
            'chaves antigas antes de concluir a rotação.'
        )
