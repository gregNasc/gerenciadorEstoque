from django.contrib.auth.models import User

class HistoricoService:

    @staticmethod
    def registrar(
        acao,
        usuario=None,
        transferencia=None,
        dados=None,
    ):
        """
        Registra eventos no histórico.
        """

        Historico.objects.create(
            acao=acao,
            usuario=usuario,
            transferencia=transferencia,
            dados=dados or {}
        )