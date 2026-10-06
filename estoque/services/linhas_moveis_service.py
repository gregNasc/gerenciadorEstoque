import json
import re

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from estoque.models import (
    Base,
    CredencialLinhaMovel,
    Equipamento,
    HistoricoLinhaMovel,
    LinhaMovel,
    Perfil,
    VinculoLinhaEquipamento,
)
from estoque.policies.linhas_moveis import LinhasMoveisAccessPolicy


class LinhasMoveisCredentialKeyring:
    CONFIG_NAME = 'LINHAS_MOVEIS_CREDENTIAL_KEYS'
    ID_PATTERN = re.compile(r'^[A-Za-z0-9_.-]{1,50}$')

    @classmethod
    def _keys(cls):
        entries = getattr(settings, cls.CONFIG_NAME, ()) or ()
        parsed = []
        identifiers = set()
        for entry in entries:
            key_id, separator, raw_key = str(entry).partition(':')
            key_id = key_id.strip()
            raw_key = raw_key.strip()
            if not separator or not cls.ID_PATTERN.fullmatch(key_id) or not raw_key:
                raise ImproperlyConfigured(
                    f'{cls.CONFIG_NAME} possui uma entrada inválida.'
                )
            if key_id in identifiers:
                raise ImproperlyConfigured(
                    f'{cls.CONFIG_NAME} possui identificadores duplicados.'
                )
            try:
                fernet = Fernet(raw_key.encode('ascii'))
            except (UnicodeEncodeError, ValueError) as exc:
                raise ImproperlyConfigured(
                    f'{cls.CONFIG_NAME} possui uma chave Fernet inválida.'
                ) from exc
            identifiers.add(key_id)
            parsed.append((key_id, fernet))
        if not parsed:
            raise ImproperlyConfigured(
                f'{cls.CONFIG_NAME} deve ser configurada para operar PIN/PUK.'
            )
        return tuple(parsed)

    @classmethod
    def encrypt(cls, payload):
        key_id, fernet = cls._keys()[0]
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
        ).encode('utf-8')
        return key_id, fernet.encrypt(serialized).decode('ascii')

    @classmethod
    def decrypt(cls, *, key_id, token):
        keys = dict(cls._keys())
        fernet = keys.get(key_id)
        if fernet is None:
            raise ImproperlyConfigured(
                'A chave necessária para esta credencial não está configurada.'
            )
        try:
            decrypted = fernet.decrypt(token.encode('ascii'))
            payload = json.loads(decrypted.decode('utf-8'))
        except (InvalidToken, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ValidationError('A credencial protegida não pôde ser descriptografada.') from exc
        if not isinstance(payload, dict):
            raise ValidationError('A credencial protegida possui formato inválido.')
        return payload


class CredenciaisLinhaMovelService:
    CAMPOS = ('pin', 'pin2', 'puk', 'puk2')
    MASK = '••••'

    @classmethod
    def _normalizar(cls, valores):
        payload = {}
        errors = {}
        for campo in cls.CAMPOS:
            valor = valores.get(campo)
            if valor is None:
                continue
            valor = str(valor).strip()
            if not valor:
                continue
            if not valor.isdigit() or not 4 <= len(valor) <= 16:
                errors[campo] = 'Informe de 4 a 16 dígitos.'
            else:
                payload[campo] = valor
        if errors:
            raise ValidationError(errors)
        return payload

    @staticmethod
    def _historico(linha, usuario, configuradas):
        HistoricoLinhaMovel.objects.create(
            empresa=linha.empresa,
            linha=linha,
            evento=HistoricoLinhaMovel.Evento.ALTERACAO,
            autor=usuario,
            metadados={
                'credenciais_configuradas': bool(configuradas),
                'quantidade_credenciais': len(configuradas),
            },
        )

    @classmethod
    @transaction.atomic
    def salvar(cls, *, usuario, linha_id, pin=None, pin2=None, puk=None, puk2=None):
        LinhasMoveisAccessPolicy.exigir(usuario, LinhasMoveisAccessPolicy.MANAGE)
        LinhasMoveisAccessPolicy.exigir(usuario, LinhasMoveisAccessPolicy.VIEW_SECRETS)
        linha = LinhasMoveisAccessPolicy.obter_linha(
            usuario,
            linha_id,
            action=LinhasMoveisAccessPolicy.MANAGE,
            for_update=True,
        )
        payload = cls._normalizar({
            'pin': pin,
            'pin2': pin2,
            'puk': puk,
            'puk2': puk2,
        })
        existente = CredencialLinhaMovel.objects.select_for_update().filter(
            linha=linha,
        ).first()
        if not payload:
            if existente is not None:
                existente.delete()
            cls._historico(linha, usuario, ())
            return None

        key_id, encrypted = LinhasMoveisCredentialKeyring.encrypt(payload)
        if existente is None:
            credencial = CredencialLinhaMovel(
                linha=linha,
                atualizado_por=usuario,
            )
        else:
            credencial = existente
        credencial.conteudo_criptografado = encrypted
        credencial.chave_id = key_id
        credencial.campos_configurados = list(payload)
        credencial.atualizado_por = usuario
        credencial.save()
        cls._historico(linha, usuario, payload)
        return credencial

    @classmethod
    def mascaradas(cls, *, usuario, linha_id):
        linha = LinhasMoveisAccessPolicy.obter_linha(
            usuario,
            linha_id,
            action=LinhasMoveisAccessPolicy.VIEW,
        )
        credencial = CredencialLinhaMovel.objects.filter(linha=linha).first()
        if credencial is None:
            return {}
        return {campo: cls.MASK for campo in credencial.campos_configurados}

    @classmethod
    def ler(cls, *, usuario, linha_id):
        LinhasMoveisAccessPolicy.exigir(usuario, LinhasMoveisAccessPolicy.VIEW_SECRETS)
        linha = LinhasMoveisAccessPolicy.obter_linha(
            usuario,
            linha_id,
            action=LinhasMoveisAccessPolicy.VIEW,
        )
        try:
            credencial = LinhasMoveisAccessPolicy.credenciais(usuario).get(linha=linha)
        except CredencialLinhaMovel.DoesNotExist:
            return {}
        return LinhasMoveisCredentialKeyring.decrypt(
            key_id=credencial.chave_id,
            token=credencial.conteudo_criptografado,
        )


class LinhasMoveisService:
    @staticmethod
    def projecao_publica_por_equipamento(*, usuario, equipamentos):
        """Retorna somente dados de conectividade liberados para integrações.

        Esta é a fronteira comum de APIs, Tory e notificações. ICCID e o modelo
        de credenciais protegidas deliberadamente não fazem parte da projeção.
        """
        equipamentos_ids = {
            getattr(equipamento, 'pk', equipamento)
            for equipamento in equipamentos
            if getattr(equipamento, 'pk', equipamento) is not None
        }
        if not equipamentos_ids:
            return {}

        linhas_visiveis = LinhasMoveisAccessPolicy.linhas(
            usuario,
            action=LinhasMoveisAccessPolicy.VIEW,
        )
        vinculos = VinculoLinhaEquipamento.objects.filter(
            equipamento_id__in=equipamentos_ids,
            fim_em__isnull=True,
            linha__in=linhas_visiveis,
        ).select_related('linha__operadora')
        return {
            vinculo.equipamento_id: {
                'numero': vinculo.linha.numero_formatado,
                'operadora': vinculo.linha.operadora.nome,
            }
            for vinculo in vinculos
        }

    @staticmethod
    def _texto_obrigatorio(valor, campo):
        valor = (valor or '').strip()
        if not valor:
            raise ValidationError({campo: 'Este campo é obrigatório.'})
        return valor

    @staticmethod
    def _historico(*, linha, usuario, evento, metadados=None):
        return HistoricoLinhaMovel.objects.create(
            empresa=linha.empresa,
            linha=linha,
            evento=evento,
            autor=usuario,
            metadados=metadados or {},
        )

    @staticmethod
    def _notificar_movimentacao(*, linha, equipamento, usuario, evento):
        from estoque.services.comunicado_service import ComunicadoService

        rotulos = {
            HistoricoLinhaMovel.Evento.VINCULO: ('Linha móvel vinculada', 'vinculada ao'),
            HistoricoLinhaMovel.Evento.TROCA: ('Linha móvel substituída', 'associada ao'),
            HistoricoLinhaMovel.Evento.DESVINCULO: ('Linha móvel desvinculada', 'desvinculada do'),
        }
        titulo, acao = rotulos[evento]
        identificador = equipamento.patrimonio or equipamento.numero_serie or equipamento.codigo
        return ComunicadoService.criar_acao(
            titulo=titulo,
            mensagem=(
                f'A linha {linha.numero_formatado} ({linha.operadora.nome}) foi {acao} '
                f'equipamento {identificador or equipamento.pk}.'
            ),
            usuario=usuario,
            tipo='OPERACIONAL',
            empresa=linha.empresa,
            dados={
                'evento': evento,
                'linha_id': linha.pk,
                'equipamento_id': equipamento.pk,
                'base_id': linha.base_id,
            },
            url=f'/equipamento/{equipamento.pk}/editar/',
        )

    @staticmethod
    def _equipamento_no_escopo(*, usuario, linha, equipamento_id):
        queryset = Equipamento.objects.select_for_update(of=('self',)).select_related(
            'produto', 'regional__empresa',
        ).filter(
            pk=equipamento_id,
            regional_id=linha.base_id,
            regional__empresa_id=linha.empresa_id,
        )
        perfil = getattr(usuario, 'perfil', None)
        if not usuario.is_superuser and (not perfil or perfil.role != Perfil.Role.ADMIN):
            queryset = queryset.filter(
                regional_id__in=perfil.regionais.values_list('pk', flat=True)
                if perfil else (),
            )
        try:
            return queryset.get()
        except Equipamento.DoesNotExist as exc:
            raise PermissionDenied('Equipamento inexistente ou fora do escopo.') from exc

    @classmethod
    @transaction.atomic
    def vincular(cls, *, usuario, linha_id, equipamento_id, inicio_em=None):
        LinhasMoveisAccessPolicy.exigir(usuario, LinhasMoveisAccessPolicy.LINK)
        linha = LinhasMoveisAccessPolicy.obter_linha(
            usuario,
            linha_id,
            action=LinhasMoveisAccessPolicy.LINK,
            for_update=True,
        )
        if linha.status != LinhaMovel.Status.DISPONIVEL:
            raise ValidationError('A linha não está disponível para vínculo.')
        equipamento = cls._equipamento_no_escopo(
            usuario=usuario,
            linha=linha,
            equipamento_id=equipamento_id,
        )
        if VinculoLinhaEquipamento.objects.select_for_update().filter(
            linha=linha,
            fim_em__isnull=True,
        ).exists():
            raise ValidationError('A linha já possui vínculo ativo.')
        if VinculoLinhaEquipamento.objects.select_for_update().filter(
            equipamento=equipamento,
            fim_em__isnull=True,
        ).exists():
            raise ValidationError('O equipamento já possui linha ativa.')

        vinculo = VinculoLinhaEquipamento.objects.create(
            linha=linha,
            equipamento=equipamento,
            inicio_em=inicio_em or timezone.now(),
            vinculado_por=usuario,
        )
        linha.status = LinhaMovel.Status.EM_USO
        linha.ativada_em = linha.ativada_em or vinculo.inicio_em
        linha.inativada_em = None
        linha.save(update_fields=('status', 'ativada_em', 'inativada_em', 'atualizado_em'))
        cls._historico(
            linha=linha,
            usuario=usuario,
            evento=HistoricoLinhaMovel.Evento.VINCULO,
            metadados={
                'equipamento_id': equipamento.pk,
                'base_id': linha.base_id,
                'vinculo_id': vinculo.pk,
            },
        )
        cls._notificar_movimentacao(
            linha=linha,
            equipamento=equipamento,
            usuario=usuario,
            evento=HistoricoLinhaMovel.Evento.VINCULO,
        )
        return vinculo

    @classmethod
    @transaction.atomic
    def trocar(cls, *, usuario, equipamento_id, nova_linha_id, motivo):
        LinhasMoveisAccessPolicy.exigir(usuario, LinhasMoveisAccessPolicy.LINK)
        motivo = cls._texto_obrigatorio(motivo, 'motivo')
        nova_linha = LinhasMoveisAccessPolicy.obter_linha(
            usuario,
            nova_linha_id,
            action=LinhasMoveisAccessPolicy.LINK,
            for_update=True,
        )
        if nova_linha.status != LinhaMovel.Status.DISPONIVEL:
            raise ValidationError('A nova linha não está disponível para vínculo.')
        equipamento = cls._equipamento_no_escopo(
            usuario=usuario,
            linha=nova_linha,
            equipamento_id=equipamento_id,
        )
        try:
            vinculo_anterior = VinculoLinhaEquipamento.objects.select_for_update().select_related(
                'linha',
            ).get(equipamento=equipamento, fim_em__isnull=True)
        except VinculoLinhaEquipamento.DoesNotExist as exc:
            raise ValidationError('O equipamento não possui linha ativa para troca.') from exc
        if vinculo_anterior.linha_id == nova_linha.pk:
            raise ValidationError('Selecione uma linha diferente para realizar a troca.')

        momento = timezone.now()
        linha_anterior = vinculo_anterior.linha
        vinculo_anterior.fim_em = momento
        vinculo_anterior.motivo_fim = motivo
        vinculo_anterior.desvinculado_por = usuario
        vinculo_anterior.save(update_fields=('fim_em', 'motivo_fim', 'desvinculado_por'))
        linha_anterior.status = LinhaMovel.Status.DISPONIVEL
        linha_anterior.save(update_fields=('status', 'atualizado_em'))

        novo_vinculo = VinculoLinhaEquipamento.objects.create(
            linha=nova_linha,
            equipamento=equipamento,
            inicio_em=momento,
            vinculado_por=usuario,
        )
        nova_linha.status = LinhaMovel.Status.EM_USO
        nova_linha.ativada_em = nova_linha.ativada_em or momento
        nova_linha.inativada_em = None
        nova_linha.save(update_fields=('status', 'ativada_em', 'inativada_em', 'atualizado_em'))
        metadados = {
            'equipamento_id': equipamento.pk,
            'vinculo_anterior_id': vinculo_anterior.pk,
            'novo_vinculo_id': novo_vinculo.pk,
            'linha_anterior_id': linha_anterior.pk,
            'nova_linha_id': nova_linha.pk,
            'motivo': motivo,
        }
        cls._historico(
            linha=linha_anterior,
            usuario=usuario,
            evento=HistoricoLinhaMovel.Evento.TROCA,
            metadados=metadados,
        )
        cls._historico(
            linha=nova_linha,
            usuario=usuario,
            evento=HistoricoLinhaMovel.Evento.TROCA,
            metadados=metadados,
        )
        cls._notificar_movimentacao(
            linha=nova_linha,
            equipamento=equipamento,
            usuario=usuario,
            evento=HistoricoLinhaMovel.Evento.TROCA,
        )
        return vinculo_anterior, novo_vinculo

    @classmethod
    @transaction.atomic
    def preparar_transferencia_base(cls, *, usuario, equipamento, nova_base):
        """Move a guarda da linha com o equipamento ou bloqueia troca de tenant."""
        if not isinstance(nova_base, Base):
            nova_base = Base.objects.select_related('empresa').get(pk=nova_base)
        vinculo = VinculoLinhaEquipamento.objects.select_for_update().select_related(
            'linha__empresa',
        ).filter(
            equipamento=equipamento,
            fim_em__isnull=True,
        ).first()
        if vinculo is None or vinculo.linha.base_id == nova_base.pk:
            return vinculo
        linha = vinculo.linha
        if linha.empresa_id != nova_base.empresa_id:
            raise ValidationError(
                'Desvincule a linha móvel antes de transferir o equipamento para outra empresa.'
            )
        base_anterior_id = linha.base_id
        linha.base = nova_base
        linha.save(update_fields=('base', 'atualizado_em'))
        cls._historico(
            linha=linha,
            usuario=usuario,
            evento=HistoricoLinhaMovel.Evento.ALTERACAO,
            metadados={
                'equipamento_id': equipamento.pk,
                'base_anterior_id': base_anterior_id,
                'nova_base_id': nova_base.pk,
                'motivo': 'Transferência de Base do equipamento vinculado.',
            },
        )
        return vinculo

    @classmethod
    @transaction.atomic
    def desvincular(cls, *, usuario, linha_id, motivo, fim_em=None):
        LinhasMoveisAccessPolicy.exigir(usuario, LinhasMoveisAccessPolicy.LINK)
        motivo = cls._texto_obrigatorio(motivo, 'motivo')
        linha = LinhasMoveisAccessPolicy.obter_linha(
            usuario,
            linha_id,
            action=LinhasMoveisAccessPolicy.LINK,
            for_update=True,
        )
        try:
            vinculo = VinculoLinhaEquipamento.objects.select_for_update().get(
                linha=linha,
                fim_em__isnull=True,
            )
        except VinculoLinhaEquipamento.DoesNotExist as exc:
            raise ValidationError('A linha não possui vínculo ativo.') from exc
        vinculo.fim_em = fim_em or timezone.now()
        vinculo.motivo_fim = motivo
        vinculo.desvinculado_por = usuario
        vinculo.save(update_fields=('fim_em', 'motivo_fim', 'desvinculado_por'))
        linha.status = LinhaMovel.Status.DISPONIVEL
        linha.save(update_fields=('status', 'atualizado_em'))
        cls._historico(
            linha=linha,
            usuario=usuario,
            evento=HistoricoLinhaMovel.Evento.DESVINCULO,
            metadados={
                'equipamento_id': vinculo.equipamento_id,
                'base_id': linha.base_id,
                'vinculo_id': vinculo.pk,
                'motivo': motivo,
            },
        )
        cls._notificar_movimentacao(
            linha=linha,
            equipamento=vinculo.equipamento,
            usuario=usuario,
            evento=HistoricoLinhaMovel.Evento.DESVINCULO,
        )
        return vinculo

    @classmethod
    @transaction.atomic
    def inativar(cls, *, usuario, linha_id, motivo):
        LinhasMoveisAccessPolicy.exigir(usuario, LinhasMoveisAccessPolicy.MANAGE)
        motivo = cls._texto_obrigatorio(motivo, 'motivo')
        linha = LinhasMoveisAccessPolicy.obter_linha(
            usuario,
            linha_id,
            action=LinhasMoveisAccessPolicy.MANAGE,
            for_update=True,
        )
        vinculo = VinculoLinhaEquipamento.objects.select_for_update().filter(
            linha=linha,
            fim_em__isnull=True,
        ).first()
        if vinculo is not None:
            vinculo.fim_em = timezone.now()
            vinculo.motivo_fim = motivo
            vinculo.desvinculado_por = usuario
            vinculo.save(update_fields=('fim_em', 'motivo_fim', 'desvinculado_por'))
        linha.status = LinhaMovel.Status.INATIVA
        linha.inativada_em = timezone.now()
        linha.save(update_fields=('status', 'inativada_em', 'atualizado_em'))
        cls._historico(
            linha=linha,
            usuario=usuario,
            evento=HistoricoLinhaMovel.Evento.INATIVACAO,
            metadados={
                'motivo': motivo,
                'vinculo_encerrado_id': vinculo.pk if vinculo else None,
            },
        )
        return linha

    @classmethod
    @transaction.atomic
    def reativar(cls, *, usuario, linha_id):
        LinhasMoveisAccessPolicy.exigir(usuario, LinhasMoveisAccessPolicy.MANAGE)
        linha = LinhasMoveisAccessPolicy.obter_linha(
            usuario,
            linha_id,
            action=LinhasMoveisAccessPolicy.MANAGE,
            for_update=True,
        )
        if linha.status not in {LinhaMovel.Status.INATIVA, LinhaMovel.Status.SUSPENSA}:
            raise ValidationError('Somente linhas inativas ou suspensas podem ser reativadas.')
        linha.status = LinhaMovel.Status.DISPONIVEL
        linha.inativada_em = None
        linha.save(update_fields=('status', 'inativada_em', 'atualizado_em'))
        cls._historico(
            linha=linha,
            usuario=usuario,
            evento=HistoricoLinhaMovel.Evento.ATIVACAO,
        )
        return linha
