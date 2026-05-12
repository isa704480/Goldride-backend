import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from realtime.routing import websocket_urlpatterns
from realtime.middleware import JWTAuthMiddleware
from channels.security.websocket import AllowedHostsOriginValidator

print("[ASGI] Starting ASGI application...")
application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AllowedHostsOriginValidator(
        JWTAuthMiddleware(
            URLRouter(websocket_urlpatterns)
        )
    ),
})
print("[ASGI] ProtocolTypeRouter configured.")

