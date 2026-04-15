from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'browser-stream/?$', consumers.VoiceReceptionistConsumer.as_asgi()),
]
