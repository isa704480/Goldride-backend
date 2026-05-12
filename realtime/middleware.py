from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from urllib.parse import parse_qs

User = get_user_model()


@database_sync_to_async
def get_user(user_id):
    try:
        return User.objects.get(id=user_id)
    except Exception:
        return AnonymousUser()

def JWTAuthMiddleware(inner):
    """
    Function-based ASGI Middleware that extracts JWT token from query string.
    """
    async def middleware(scope, receive, send):
        if scope['type'] in ['websocket', 'http']:
            try:
                query_string = scope.get('query_string', b'').decode()
                params = parse_qs(query_string)
                token_str = params.get('token', [None])[0]

                if token_str:
                    try:
                        token = AccessToken(token_str)
                        user_id = token.get('user_id') or token.get('id')
                        user = await get_user(user_id)
                        print(f"[WS] Connection attempt: User ID {user_id}, Found: {user.is_authenticated}")
                        scope['user'] = user
                    except Exception as e:
                        print(f"[WS] Token validation failed: {e}")
                        scope['user'] = AnonymousUser()
                else:
                    print("[WS] No token in query string")
                    scope['user'] = AnonymousUser()
            except Exception as e:
                print(f"[WS] Middleware error: {e}")
                scope['user'] = AnonymousUser()

        return await inner(scope, receive, send)
    
    return middleware
