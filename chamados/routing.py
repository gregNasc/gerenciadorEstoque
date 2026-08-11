from django.urls import path

from chamados.consumers import ChamadoChatConsumer


websocket_urlpatterns = [
    path('ws/chamados/<int:pk>/', ChamadoChatConsumer.as_asgi()),
]
