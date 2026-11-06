import unicodedata

from django.db import migrations
from django.db.models import Q
from django.utils import timezone


EVENTOS_RECEBIMENTO = {
    'NFE_PROCESSADA',
    'NFE_ITEM_CATALOGO_CONFIRMADO',
    'REMESSA_CRIADA',
    'REMESSA_ENVIADA',
    'REMESSA_CONFERIDA',
    'RECEBIMENTO_DIVERGENTE',
    'EQUIPAMENTO_INDIVIDUALIZADO',
}


def _normalizar(valor):
    texto = unicodedata.normalize('NFKD', str(valor or ''))
    return ''.join(char for char in texto if not unicodedata.combining(char)).lower()


def _assunto_bloqueado(comunicado):
    dados = comunicado.dados or {}
    evento = str(dados.get('evento') or dados.get('evento_custodia') or '').upper()
    template = _normalizar(dados.get('template_codigo'))
    conteudo = _normalizar(
        f'{comunicado.titulo} {comunicado.mensagem} {template}'
    )
    return bool(
        dados.get('conteudo_financeiro')
        or evento in EVENTOS_RECEBIMENTO
        or dados.get('evento_custodia')
        or 'custodia' in template
        or any(token in conteudo for token in (
            'planejamento de consumo', 'planejamento',
            'identificar recebimento', 'individualizacao de recebimento',
            'custodia', 'preco', 'cotacao', 'valor financeiro',
        ))
    )


def aplicar_restricoes(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    Comunicado = apps.get_model('estoque', 'Comunicado')
    ComunicadoEntrega = apps.get_model('estoque', 'ComunicadoEntrega')
    EntregaCustodia = apps.get_model('estoque', 'EntregaNotificacaoCustodia')

    usuario = User.objects.filter(username__iexact='jose.barboza').first()
    if usuario is None:
        return

    grupos = Group.objects.filter(name='INSUMOS_PLANEJAMENTO')
    usuario.groups.remove(*grupos)
    permissoes = Permission.objects.filter(
        Q(codename__icontains='planejamento')
        | Q(codename__icontains='preco')
        | Q(codename__icontains='custodia')
        | Q(codename__icontains='individualiz')
    )
    usuario.user_permissions.remove(*permissoes)

    bloqueados = []
    for comunicado in Comunicado.objects.filter(usuarios=usuario).iterator():
        if _assunto_bloqueado(comunicado):
            bloqueados.append(comunicado.pk)
            comunicado.usuarios.remove(usuario)

    agora = timezone.now()
    ComunicadoEntrega.objects.filter(
        usuario_id=usuario.pk,
        comunicado_id__in=bloqueados,
        status__in=('PENDENTE', 'FALHA'),
    ).update(
        status='IGNORADA',
        ultimo_erro='ASSUNTO NÃO AUTORIZADO PARA O DESTINATÁRIO.',
        processada_em=agora,
        proxima_tentativa_em=None,
    )
    EntregaCustodia.objects.filter(
        Q(usuario_id=usuario.pk) | Q(colaborador__usuario_id=usuario.pk),
        status__in=('PENDENTE', 'FALHA'),
    ).update(
        status='IGNORADA',
        ultimo_erro='ASSUNTO NÃO AUTORIZADO PARA O DESTINATÁRIO.',
        processada_em=agora,
        proxima_tentativa_em=None,
    )


class Migration(migrations.Migration):
    dependencies = [
        ('estoque', '0075_perfis_inventory_latam_em_espanhol'),
    ]

    operations = [
        migrations.RunPython(aplicar_restricoes, migrations.RunPython.noop),
    ]
