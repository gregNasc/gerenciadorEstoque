from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from chamados.models import Chamado, ChamadoConexaoAtendente
from chamados.policies import ChamadoAccessPolicy
from chamados.services import ChamadoService


class PresencaChamadosConsumer(AsyncJsonWebsocketConsumer):
    """Presença de suporte e canal global de eventos do usuário autenticado."""

    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close(code=4403)
            return
        self.e_atendente = await self._pode_atender()
        self.grupos_presenca = [f'chamados_usuario_{user.pk}']
        if self.e_atendente:
            self.grupos_presenca.append('chamados_atendentes')
            await self._registrar_presenca()
        if await self._e_admin():
            self.grupos_presenca.append('chamados_admins')
        for grupo in self.grupos_presenca:
            await self.channel_layer.group_add(grupo, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        for grupo in getattr(self, 'grupos_presenca', []):
            await self.channel_layer.group_discard(grupo, self.channel_name)
        if getattr(self, 'e_atendente', False):
            await self._remover_presenca()

    async def receive_json(self, content, **kwargs):
        if content.get('tipo') == 'ping':
            if getattr(self, 'e_atendente', False):
                await self._atualizar_presenca()
            await self.send_json({'tipo': 'pong'})

    async def chamado_evento(self, event):
        await self.send_json({'tipo': 'chamado_evento', 'evento': event['payload']})

    @database_sync_to_async
    def _pode_atender(self):
        return ChamadoAccessPolicy.pode_atender(self.scope['user'])

    @database_sync_to_async
    def _e_admin(self):
        return ChamadoAccessPolicy.e_admin(self.scope['user'])

    @database_sync_to_async
    def _registrar_presenca(self):
        ChamadoConexaoAtendente.objects.update_or_create(
            canal=self.channel_name,
            defaults={'usuario': self.scope['user']},
        )

    @database_sync_to_async
    def _atualizar_presenca(self):
        ChamadoConexaoAtendente.objects.filter(canal=self.channel_name).update(
            visto_em=timezone.now(),
        )

    @database_sync_to_async
    def _remover_presenca(self):
        ChamadoConexaoAtendente.objects.filter(canal=self.channel_name).delete()


class ChamadoChatConsumer(AsyncJsonWebsocketConsumer):
    """Chat em tempo real, sempre vinculado a um chamado e à sessão autenticada."""

    async def connect(self):
        self.chamado_id = self.scope['url_route']['kwargs']['pk']
        self.grupo = f'chamado_{self.chamado_id}'
        if not await self._pode_acessar():
            await self.close(code=4403)
            return
        await self.channel_layer.group_add(self.grupo, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        grupo = getattr(self, 'grupo', None)
        if grupo:
            await self.channel_layer.group_discard(grupo, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if content.get('tipo') != 'mensagem':
            await self.send_json({'tipo': 'erro', 'mensagem': 'AÇÃO NÃO SUPORTADA.'})
            return
        texto = str(content.get('texto') or '').strip()
        if not texto:
            await self.send_json({'tipo': 'erro', 'mensagem': 'DIGITE UMA MENSAGEM.'})
            return
        if len(texto) > 10000:
            await self.send_json({'tipo': 'erro', 'mensagem': 'A MENSAGEM É MUITO LONGA.'})
            return
        try:
            item = await self._registrar_mensagem(
                texto=texto,
                nota_interna=bool(content.get('nota_interna')),
            )
        except (PermissionDenied, ValidationError) as exc:
            mensagens = getattr(exc, 'messages', None)
            await self.send_json({
                'tipo': 'erro',
                'mensagem': ' '.join(mensagens) if mensagens else str(exc),
            })
            return
        await self.channel_layer.group_send(
            self.grupo,
            {'type': 'chat.mensagem', 'mensagem_id': item['id']},
        )

    async def chat_mensagem(self, event):
        item = await self._mensagem_visivel(event['mensagem_id'])
        if item:
            await self.send_json({'tipo': 'mensagem', 'item': item})

    @database_sync_to_async
    def _pode_acessar(self):
        user = self.scope.get('user')
        return bool(
            user and user.is_authenticated
            and ChamadoAccessPolicy.queryset(user).filter(pk=self.chamado_id).exists()
        )

    @database_sync_to_async
    def _registrar_mensagem(self, *, texto, nota_interna):
        user = self.scope['user']
        chamado = Chamado.objects.get(pk=self.chamado_id)
        mensagem = ChamadoService.adicionar_mensagem(
            chamado=chamado,
            usuario=user,
            texto=texto,
            nota_interna=nota_interna,
        )
        return {'id': mensagem.pk}

    @database_sync_to_async
    def _mensagem_visivel(self, mensagem_id):
        user = self.scope['user']
        mensagem = Chamado.objects.get(pk=self.chamado_id).mensagens.select_related(
            'autor'
        ).filter(pk=mensagem_id).first()
        if not mensagem:
            return None
        if mensagem.nota_interna and not ChamadoAccessPolicy.pode_atender(user):
            return None
        return {
            'id': mensagem.pk,
            'autor_id': mensagem.autor_id,
            'autor': mensagem.autor.get_full_name() or mensagem.autor.get_username(),
            'texto': mensagem.texto,
            'nota_interna': mensagem.nota_interna,
            'criado_em': mensagem.criado_em.strftime('%d/%m/%Y %H:%M'),
        }
