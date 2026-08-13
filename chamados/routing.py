from django.urls import path

from chamados.consumers import ChamadoChatConsumer, PresencaChamadosConsumer


websocket_urlpatterns = [
    path('ws/chamados/presenca/', PresencaChamadosConsumer.as_asgi()),
    path('ws/chamados/<int:pk>/', ChamadoChatConsumer.as_asgi()),
]
