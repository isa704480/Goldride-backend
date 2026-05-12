from django.http import HttpResponse
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from urllib.parse import parse_qs

User = get_user_model()

@database_sync_to_async
def get_user(user_id):
    try:
        return User.objects.get(id=user_id)
    except:
        return AnonymousUser()

def JWTAuthMiddleware(inner):
    async def middleware(scope, receive, send):
        if scope['type'] == 'websocket':
            try:
                qs = parse_qs(scope.get('query_string', b'').decode())
                token_str = qs.get('token', [None])[0]
                if token_str:
                    token = AccessToken(token_str)
                    user_id = token.get('user_id') or token.get('id')
                    scope['user'] = await get_user(user_id)
                else:
                    scope['user'] = AnonymousUser()
            except:
                scope['user'] = AnonymousUser()
        return await inner(scope, receive, send)
    return middleware

class DebugMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Handle OPTIONS immediately before anything else
        if request.method == "OPTIONS":
            print(f"[CORS-DEBUG] Handling OPTIONS for {request.path}")
            response = HttpResponse()
            response["Access-Control-Allow-Origin"] = "*"
            response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE, PATCH"
            response["Access-Control-Allow-Headers"] = "*"
            response["Access-Control-Max-Age"] = "86400"
            return response

        print(f"[CORS-DEBUG] Request: {request.method} {request.path}")
        response = self.get_response(request)
        
        # Add headers to all responses
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE, PATCH"
        response["Access-Control-Allow-Headers"] = "*"
        
        return response
