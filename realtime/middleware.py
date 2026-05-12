from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from urllib.parse import parse_qs
from django.http import HttpResponse

User = get_user_model()

@database_sync_to_async
def get_user(user_id):
    try:
        return User.objects.get(id=user_id)
    except Exception:
        return AnonymousUser()

def JWTAuthMiddleware(inner):
    """
    Function-based ASGI Middleware for WebSockets.
    """
    async def middleware(scope, receive, send):
        if scope['type'] == 'websocket':
            query_string = scope.get('query_string', b'').decode()
            params = parse_qs(query_string)
            token_str = params.get('token', [None])[0]
            if token_str:
                try:
                    token = AccessToken(token_str)
                    user_id = token.get('user_id') or token.get('id')
                    scope['user'] = await get_user(user_id)
                except:
                    scope['user'] = AnonymousUser()
            else:
                scope['user'] = AnonymousUser()
        return await inner(scope, receive, send)
    return middleware

class DebugMiddleware:
    """
    EXTREME CORS FIX: Manually handle OPTIONS and add headers to all responses.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. Handle Preflight (OPTIONS) manually if needed
        if request.method == "OPTIONS":
            response = HttpResponse()
            response["Access-Control-Allow-Origin"] = "*"
            response["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS, PUT, DELETE, PATCH"
            response["Access-Control-Allow-Headers"] = "Accept, Content-Type, Authorization, X-Requested-With"
            response["Access-Control-Max-Age"] = "86400"
            return response

        # 2. Log the request
        print(f"[DEBUG] Request: {request.method} {request.path} from {request.META.get('HTTP_ORIGIN')}")
        
        # 3. Get response from next middleware
        response = self.get_response(request)
        
        # 4. Force CORS headers on ALL responses
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS, PUT, DELETE, PATCH"
        response["Access-Control-Allow-Headers"] = "Accept, Content-Type, Authorization, X-Requested-With"
        
        print(f"[DEBUG] Response status: {response.status_code} (CORS Headers Forced)")
        return response
