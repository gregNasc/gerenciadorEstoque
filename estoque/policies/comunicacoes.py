import unicodedata


class RestricaoComunicacaoUsuarioPolicy:
    """Restrições explícitas de assunto que independem do papel do usuário."""

    JOSE_BARBOZA = 'jose.barboza'
    EVENTOS_RECEBIMENTO = frozenset({
        'NFE_PROCESSADA',
        'NFE_ITEM_CATALOGO_CONFIRMADO',
        'REMESSA_CRIADA',
        'REMESSA_ENVIADA',
        'REMESSA_CONFERIDA',
        'RECEBIMENTO_DIVERGENTE',
        'EQUIPAMENTO_INDIVIDUALIZADO',
    })

    @staticmethod
    def _normalizar(valor):
        texto = unicodedata.normalize('NFKD', str(valor or ''))
        return ''.join(char for char in texto if not unicodedata.combining(char)).lower()

    @classmethod
    def usuario_restrito(cls, usuario):
        return bool(
            usuario
            and usuario.is_authenticated
            and usuario.get_username().strip().lower() == cls.JOSE_BARBOZA
        )

    @classmethod
    def assunto_bloqueado(cls, comunicado):
        dados = comunicado.dados or {}
        evento = str(
            dados.get('evento') or dados.get('evento_custodia') or ''
        ).strip().upper()
        template = cls._normalizar(dados.get('template_codigo'))
        conteudo = cls._normalizar(
            f'{comunicado.titulo} {comunicado.mensagem} {template}'
        )
        if dados.get('conteudo_financeiro'):
            return True
        if evento in cls.EVENTOS_RECEBIMENTO:
            return True
        if dados.get('evento_custodia') or 'custodia' in template:
            return True
        return any(token in conteudo for token in (
            'planejamento de consumo',
            'planejamento',
            'identificar recebimento',
            'individualizacao de recebimento',
            'custodia',
            'preco',
            'cotacao',
            'valor financeiro',
        ))

    @classmethod
    def pode_receber(cls, comunicado, usuario):
        return not (
            cls.usuario_restrito(usuario)
            and cls.assunto_bloqueado(comunicado)
        )

    @classmethod
    def remover_destinatarios_bloqueados(cls, comunicado):
        jose = comunicado.usuarios.filter(
            username__iexact=cls.JOSE_BARBOZA,
        ).first()
        if jose and not cls.pode_receber(comunicado, jose):
            comunicado.usuarios.remove(jose)
