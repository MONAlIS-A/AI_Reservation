from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('browser-stream/', consumers.VoiceReceptionistConsumer.as_asgi()),
    path('browser-stream', consumers.VoiceReceptionistConsumer.as_asgi()),
]
